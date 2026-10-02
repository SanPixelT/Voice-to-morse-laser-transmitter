import time, logging
from datetime import datetime
import threading, collections, queue, os, os.path
import deepspeech
import numpy as np
import pyaudio
import wave
import webrtcvad
from halo import Halo
from scipy import signal
import noisereduce as nr
import matplotlib.pyplot as plt
from scipy.io.wavfile import write
import RPi.GPIO as GPIO
import time

logging.basicConfig(level=20)

class Audio(object):
    """Streams raw audio from microphone. Data is received in a separate thread, and stored in a buffer, to be read from."""

    FORMAT = pyaudio.paInt16
    # Network/VAD rate-space
    RATE_PROCESS = 16000
    CHANNELS = 1
    BLOCKS_PER_SECOND = 50

    def __init__(self, callback=None, device=None, input_rate=RATE_PROCESS, file=None):
        def proxy_callback(in_data, frame_count, time_info, status):
            #pylint: disable=unused-argument
            if self.chunk is not None:
                in_data = self.wf.readframes(self.chunk)
            callback(in_data)
            return (None, pyaudio.paContinue)
        if callback is None: callback = lambda in_data: self.buffer_queue.put(in_data)
        self.buffer_queue = queue.Queue()
        self.device = device
        self.input_rate = input_rate
        self.sample_rate = self.RATE_PROCESS
        self.block_size = int(self.RATE_PROCESS / float(self.BLOCKS_PER_SECOND))
        self.block_size_input = int(self.input_rate / float(self.BLOCKS_PER_SECOND))
        self.pa = pyaudio.PyAudio()

        kwargs = {
            'format': self.FORMAT,
            'channels': self.CHANNELS,
            'rate': self.input_rate,
            'input': True,
            'frames_per_buffer': self.block_size_input,
            'stream_callback': proxy_callback,
        }

        self.chunk = None
        # if not default device
        if self.device:
            kwargs['input_device_index'] = self.device
        elif file is not None:
            self.chunk = 320
            self.wf = wave.open(file, 'rb')

        self.stream = self.pa.open(**kwargs)
        self.stream.start_stream()

    def resample(self, data, input_rate):
        """
        Microphone may not support our native processing sampling rate, so
        resample from input_rate to RATE_PROCESS here for webrtcvad and
        deepspeech

        Args:
            data (binary): Input audio stream
            input_rate (int): Input audio rate to resample from
        """
        data16 = np.frombuffer(buffer=data, dtype=np.int16)
        resample_size = int(len(data16) / self.input_rate * self.RATE_PROCESS)
        resample = signal.resample(data16, resample_size)
        resample16 = np.array(resample, dtype=np.int16)
        return resample16.tobytes()

    def read_resampled(self):
        """Return a block of audio data resampled to 16000hz, blocking if necessary."""
        return self.resample(data=self.buffer_queue.get(),
                             input_rate=self.input_rate)

    def read(self):
        """Return a block of audio data, blocking if necessary."""
        return self.buffer_queue.get()

    def destroy(self):
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()

    frame_duration_ms = property(lambda self: 1000 * self.block_size // self.sample_rate)

    def write_wav(self, filename, data):
        logging.info("write wav %s", filename)
        wf = wave.open(filename, 'wb')
        wf.setnchannels(self.CHANNELS)
        # wf.setsampwidth(self.pa.get_sample_size(FORMAT))
        assert self.FORMAT == pyaudio.paInt16
        wf.setsampwidth(2)
        wf.setframerate(self.sample_rate)
        wf.writeframes(data)
        wf.close()

LETTERS_TO_MC = {
    'A': '.-', 'B': '-...', 'C': '-.-.',
    'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..',
    'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---',
    'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-',
    'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',  '1': '.----',
    '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.', '0': '-----',
    ' ': '/'
    }

def translate(words):
    return " ".join(LETTERS_TO_MC[char] for char in words.upper())

def invert_spreading_code(spreading_code):
    inverted_code = []
    for chip in spreading_code:
        if chip == GPIO.HIGH:
            inverted_code.append(GPIO.LOW)
        else:
            inverted_code.append(GPIO.HIGH)
    return inverted_code

class VADAudio(Audio):
    """Filter & segment audio with voice activity detection."""

    def __init__(self, aggressiveness=3, device=None, input_rate=None, file=None):
        super().__init__(device=device, input_rate=input_rate, file=file)
        self.vad = webrtcvad.Vad(aggressiveness)

    def frame_generator(self):
        """Generator that yields all audio frames from microphone."""
        if self.input_rate == self.RATE_PROCESS:
            while True:
                yield self.read()
        else:
            while True:
                yield self.read_resampled()

    def vad_collector(self, padding_ms=500, ratio=0.75, frames=None, max_noise_frames=300):
        """Generator that yields series of consecutive audio frames comprising each utterence, separated by yielding a single None.
            Determines voice activity by ratio of frames in padding_ms. Uses a buffer to include padding_ms prior to being triggered.
            Example: (frame, ..., frame, None, frame, ..., frame, None, ...)
                      |---utterence---|        |---utterence---|
        """
        if frames is None: frames = self.frame_generator()
        num_padding_frames = padding_ms // self.frame_duration_ms
        ring_buffer = collections.deque(maxlen=num_padding_frames)
        triggered = False

        for frame in frames:
            if len(frame) < 640:
                return

            is_speech = self.vad.is_speech(frame, self.sample_rate)

            if not triggered:
                ring_buffer.append((frame, is_speech))
                num_voiced = len([f for f, speech in ring_buffer if speech])
                
                if num_voiced > ratio * ring_buffer.maxlen:
                    triggered = True
                    yield ([f for f, s in ring_buffer])
                    ring_buffer.clear()

            else:
                yield frame
                ring_buffer.append((frame, is_speech))
                num_unvoiced = len([f for f, speech in ring_buffer if not speech])
                
                if num_unvoiced > ratio * ring_buffer.maxlen:
                    # yield (None, [f for f, s in ring_buffer])
                    print(f"Frame type AFTER yield: {type(frame)}")
                    print("RESETTING")
                    triggered = False
                    yield None # Indicate end of speech segment
                    ring_buffer.clear()

GPIO.setmode(GPIO.BCM)
GPIO.setup(22, GPIO.OUT) 

unit = 0.06

dot_duration = unit # Duration of a dot           
dash_duration = 3*unit  # Duration of a dash            
element_pause = unit  # Pause between elements of a character
char_pause = 3*unit     # Pause between characters

spreading_code = [GPIO.HIGH, GPIO.LOW, GPIO.HIGH, GPIO.LOW] 
inverted_spreading_code = invert_spreading_code(spreading_code)

def transmit_morse(morse_code):
    chip_duration = dot_duration / len(spreading_code) # Duration of each chip 
    
    for element in morse_code:
        if element == '.':
            for chip in spreading_code:
                GPIO.output(17, chip)
                time.sleep(chip_duration)
        elif element == '-':
            for _ in range(3):
                for chip in spreading_code:
                    GPIO.output(22, chip)
                    time.sleep(chip_duration)
        for chip in inverted_spreading_code:
            GPIO.output(22, chip)
            time.sleep(chip_duration) #emulates element pause
    time.sleep(char_pause)
    GPIO.output(22, GPIO.LOW)

def main(ARGS):
    # Load DeepSpeech model
    if os.path.isdir(ARGS.model):
        model_dir = ARGS.model
        ARGS.model = os.path.join(model_dir, 'output_graph.pb')
        ARGS.scorer = os.path.join(model_dir, ARGS.scorer)

    print('Initializing model...')
    logging.info("ARGS.model: %s", ARGS.model)
    model = deepspeech.Model(ARGS.model)
    if ARGS.scorer:
        logging.info("ARGS.scorer: %s", ARGS.scorer)
        model.enableExternalScorer(ARGS.scorer)

    # Start audio with VAD
    vad_audio = VADAudio(aggressiveness=ARGS.vad_aggressiveness,
                         device=ARGS.device,
                         input_rate=ARGS.rate,
                         file=ARGS.file)
    
    print("Listening (ctrl-C to exit)...")
    collected_frames = vad_audio.vad_collector()
    
    # Stream from microphone to DeepSpeech using VAD
    spinner = None
    if not ARGS.nospinner:
        spinner = Halo(spinner='line')
    stream_context = model.createStream()
    wav_data = bytearray()
    triggered_1 = False

    for frame in collected_frames:
        if frame  is not None:
            if not triggered_1:
                # Process a list of frames
                if spinner: spinner.start()
                y = np.concatenate([np.frombuffer(f, np.int16) for f in frame])
                y_noise = np.concatenate([np.frombuffer(f, np.int16) for f in frame])
                triggered_1 = True  # Set flag to true after first iteration with speech frames
            else:
                # Process individual frames
                if isinstance(frame, bytes):
                    y_dummy = np.frombuffer(frame, np.int16)
                    y = np.concatenate((y, y_dummy))
                
        if frame is None:
            if spinner: spinner.stop()
            logging.debug("streaming frame")
            
            if y.size > 0 and y_noise.size > 0:
                triggered_1 = False 
                reduced_noise_speech = nr.reduce_noise(y=y, y_noise=y_noise, sr=16000, thresh_n_mult_nonstationary = 1, n_std_thresh_stationary = 0.9)
                reduced_noise_speech_bytes = reduced_noise_speech.astype(np.int16).tobytes()
                stream_context.feedAudioContent(np.frombuffer(reduced_noise_speech_bytes, np.int16))
                
                # plt.figure(figsize=(12, 6))
                # plt.subplot(2, 1, 1)
                # plt.plot(y)
                # plt.title("Original Audio")
                # plt.xlabel("Sample")
                # plt.ylabel("Amplitude")

                # plt.subplot(2, 1, 2)
                # plt.plot(reduced_noise_speech)
                # plt.title("Audio After Noise Reduction")
                # plt.xlabel("Sample")
                # plt.ylabel("Amplitude")

                # plt.tight_layout()
                # plt.show()                
                
                write("original_audio.wav", 16000, y.astype(np.int16))
                write("noise_reduced_audio.wav", 16000, reduced_noise_speech.astype(np.int16))
                if ARGS.savewav: 
                    wav_data.extend(reduced_noise_speech_bytes)
            logging.debug("end utterence")
            y = np.array([], dtype=np.int16)  # Reset speech buffer
            y_noise = np.array([], dtype=np.int16)  # Reset noise buffer

            if ARGS.savewav:
                vad_audio.write_wav(os.path.join(ARGS.savewav, datetime.now().strftime("savewav_%Y-%m-%d_%H-%M-%S_%f.wav")), wav_data)
                wav_data = bytearray()
            text = stream_context.finishStream()
            print("Recognized: %s" % text)
            print(translate(text))

            # Morse
            morse_message = translate(text)
            for char in morse_message.split(' '):
                transmit_morse(char)
            GPIO.cleanup()
            
            print("Done transmitting, waiting 20 seconds")
            time.sleep(5)
            
            stream_context = model.createStream()
            
            


if __name__ == '__main__':
    DEFAULT_SAMPLE_RATE = 16000

    import argparse
    parser = argparse.ArgumentParser(description="Stream from microphone to DeepSpeech using VAD")

    parser.add_argument('-v', '--vad_aggressiveness', type=int, default=3,
                        help="Set aggressiveness of VAD: an integer between 0 and 3, 0 being the least aggressive about filtering out non-speech, 3 the most aggressive. Default: 3")
    parser.add_argument('--nospinner', action='store_true',
                        help="Disable spinner")
    parser.add_argument('-w', '--savewav',
                        help="Save .wav files of utterences to given directory")
    parser.add_argument('-f', '--file',
                        help="Read from .wav file instead of microphone")

    parser.add_argument('-m', '--model', required=True,
                        help="Path to the model (protocol buffer binary file, or entire directory containing all standard-named files for model)")
    parser.add_argument('-s', '--scorer',
                        help="Path to the external scorer file.")
    parser.add_argument('-d', '--device', type=int, default=None,
                        help="Device input index (Int) as listed by pyaudio.PyAudio.get_device_info_by_index(). If not provided, falls back to PyAudio.get_default_device().")
    parser.add_argument('-r', '--rate', type=int, default=DEFAULT_SAMPLE_RATE,
                        help=f"Input device sample rate. Default: {DEFAULT_SAMPLE_RATE}. Your device may require 44100.")

    ARGS = parser.parse_args()
    if ARGS.savewav: os.makedirs(ARGS.savewav, exist_ok=True)
    main(ARGS)
