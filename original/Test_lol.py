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
import time

logging.basicConfig(level=20)

class Audio(object):
    """
    Manages streaming raw audio from a microphone. Captures data on a separate thread and stores it in a queue for further processing.
    """
    CHANNELS = 1
    FORMAT = pyaudio.paInt16
    BLOCKS_PER_SECOND = 50
    RATE_PROCESS = 16000
    
    def __init__(self, device=None, callback=None,  file=None, input_rate=RATE_PROCESS):
        def proxy_callback(in_data, frame_count, time_info, status):
            if self.chunk is not None:
                in_data = self.wf.readframes(self.chunk)
            callback(in_data)
            return (None, pyaudio.paContinue)
        if callback is None: callback = lambda in_data: self.buffer_queue.put(in_data)
        
        self.input_rate = input_rate
        self.buffer_queue = queue.Queue()
        self.sample_rate = self.RATE_PROCESS
        self.device = device
        self.block_size = int(self.RATE_PROCESS / float(self.BLOCKS_PER_SECOND))
        self.pa = pyaudio.PyAudio()
        self.block_size_input = int(self.input_rate / float(self.BLOCKS_PER_SECOND))
        

        kwargs = {
            'channels': self.CHANNELS,
            'format': self.FORMAT,
            'rate': self.input_rate,
            'input': True,
            'stream_callback': proxy_callback,
            'frames_per_buffer': self.block_size_input,
        }

        self.chunk = None
        if self.device:
            kwargs['input_device_index'] = self.device
        elif file is not None:
            self.chunk = 320
            self.wf = wave.open(file, 'rb')

        self.stream = self.pa.open(**kwargs)
        self.stream.start_stream()

    def resample(self, data, input_rate):
        """resample from input_rate to RATE_PROCESS here for webrtcvad and deepspeech, both at 16 kHZ"""
        
        data16 = np.frombuffer(buffer=data, dtype=np.int16)
        first_resample_size = int(len(data16) / self.input_rate * self.RATE_PROCESS)
        x = signal.resample(data16, first_resample_size)
        resample16 = np.array(x, dtype=np.int16)
        return resample16.tobytes()

    def read_12resampled(self):
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

    frame12_duration12_ms = property(lambda self: 1000 * self.block_size // self.sample_rate)

    def write_12wav(self, filename, data):
        logging.info("write wav %s", filename)
        wavefile = wave.open(filename, 'wb')
        wavefile.setnchannels(self.CHANNELS)
        assert self.FORMAT == pyaudio.paInt16
        wavefile.setsampwidth(2)
        wavefile.setframerate(self.sample_rate)
        wavefile.writeframes(data)
        wavefile.close()
        
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
    ' ': '/',"'":'.'   
    }

def translate(words):
    return " ".join(LETTERS_TO_MC[char] for char in words.upper())


class VADAudio(Audio):
    """
    Extends Audio to filter and segment audio using voice activity detection (VAD).
    """

    def __init__(self, input_rate=None, aggressiveness=3, file=None, device=None):
        super().__init__(input_rate=input_rate, device=device, file=file)
        self.vad = webrtcvad.Vad(aggressiveness)

    def frame_12generator(self):
        """Generator that yields all audio frames from microphone."""
        if self.input_rate == self.RATE_PROCESS:
            while True:
                yield self.read()
        else:
            while True:
                yield self.read_12resampled()

    def vad_collector(self, ratio=0.4, padding_ms=500, max_noise_frames=200, frames=None):
        """
        Generator that yields sequences of consecutive audio frames comprising speech, separated by a single None to denote pauses.
        """
        if frames is None: frames = self.frame_12generator()
        num_padding_frames = padding_ms // self.frame12_duration12_ms
        buffer_frame = collections.deque(maxlen=num_padding_frames)
        triggered = False
        
        try:
            for frame in frames:
                if len(frame) < 640:
                    return

                is_speech = self.vad.is_speech(frame, self.sample_rate)

                if not triggered:
                    buffer_frame.append((frame, is_speech))
                    num_voiced = len([f for f, speech in buffer_frame if speech])
                    
                    if num_voiced > 0.6 * ratio * buffer_frame.maxlen:
                        triggered = True
                        yield ([f for f, s in buffer_frame])
                        buffer_frame.clear()

                else:
                    yield frame
                    buffer_frame.append((frame, is_speech))
                    num_unvoiced = len([f for f, speech in buffer_frame if not speech])
                    
                    if num_unvoiced > 1.4 * ratio * buffer_frame.maxlen:
                        print("RESETTING")
                        triggered = False
                        yield None # Indicate end of speech segment
                        buffer_frame.clear()
                    
        finally:
            # Handle any remaining speech data in the buffer
            if triggered or len(buffer_frame) > 0:
                yield [f for f, s in buffer_frame]
            yield None  # Ensure a final None is always yielded to signal the end
                
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
                #reduced_noise_speech = nr.reduce_noise(y=y, sr=16000)
                reduced_noise_speech = nr.reduce_noise(y=y, sr=16000, thresh_n_mult_nonstationary=1.2,stationary=False,n_fft=512,time_mask_smooth_ms=150, prop_decrease=0.8,n_jobs=-1, freq_mask_smooth_hz=400,win_length=256) 
                reduced_noise_speech_bytes = reduced_noise_speech.astype(np.int16).tobytes()
                stream_context.feedAudioContent(np.frombuffer(y, np.int16))
                
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
                vad_audio.write_12wav(os.path.join(ARGS.savewav, datetime.now().strftime("savewav_%Y-%m-%d_%H-%M-%S_%f.wav")), wav_data)
                wav_data = bytearray()
            text = stream_context.finishStream()
            print("Recognized: %s" % text)
            print("Recognized: %s" % translate(text))
            stream_context = model.createStream()
            #time.sleep(4)

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
    
   