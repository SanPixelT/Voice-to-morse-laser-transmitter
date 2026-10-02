# Voice-to-Morse laser transmitter (runs on the Raspberry Pi 4).
# Mic -> voice activity detection -> noise reduction -> DeepSpeech -> Morse -> GPIO pin 22,
# which switches the laser driver transistor (OOK). Each Morse element is sent as a
# short spreading code (DSSS) instead of a plain on/off pulse.
#
# Based on mic_vad_streaming.py from Mozilla's DeepSpeech examples
# (https://github.com/mozilla/DeepSpeech-examples, Mozilla Public License 2.0).
# The Audio class and argument parsing are mostly theirs; the noise reduction,
# Morse translation and GPIO/DSSS transmission are mine.
#
# Example:
#   python pi_transmitter.py -m deepspeech-0.9.3-models.pbmm -s deepspeech-0.9.3-models.scorer -r 48000

import time, logging
from datetime import datetime
import collections, queue, os, os.path
import deepspeech
import numpy as np
import pyaudio
import wave
import webrtcvad
from halo import Halo
from scipy import signal
import noisereduce as nr
import RPi.GPIO as GPIO

logging.basicConfig(level=20)

LASER_PIN = 22  # BCM numbering


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
    ' ': '/', "'": '.----.'
    }

def translate(words):
    # skip anything without a Morse code instead of crashing
    return " ".join(LETTERS_TO_MC[char] for char in words.upper() if char in LETTERS_TO_MC)

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

    def vad_collector(self, padding_ms=500, ratio=0.75, frames=None):
        """Yields a list of frames when speech starts, then single frames, then None when it stops."""
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
                    triggered = False
                    yield None # Indicate end of speech segment
                    ring_buffer.clear()


# Morse timing (unit = dot length)
unit = 0.06
dot_duration = unit
dash_duration = 3*unit
element_pause = unit
char_pause = 3*unit

# DSSS: a "1" (light on) is sent as the spreading code and a "0" (gap) as the inverted code,
# so the laser is always toggling and the receiver needs the code to recover the message.
spreading_code = [GPIO.HIGH, GPIO.LOW, GPIO.HIGH, GPIO.LOW]
inverted_spreading_code = invert_spreading_code(spreading_code)

def transmit_morse(morse_code):
    chip_duration = dot_duration / len(spreading_code) # Duration of each chip

    for element in morse_code:
        if element == '.':
            for chip in spreading_code:
                GPIO.output(LASER_PIN, chip)
                time.sleep(chip_duration)
        elif element == '-':
            for _ in range(3):
                for chip in spreading_code:
                    GPIO.output(LASER_PIN, chip)
                    time.sleep(chip_duration)
        for chip in inverted_spreading_code:
            GPIO.output(LASER_PIN, chip)
            time.sleep(chip_duration) # element pause
    time.sleep(char_pause)
    GPIO.output(LASER_PIN, GPIO.LOW)

def main(ARGS):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LASER_PIN, GPIO.OUT)

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
    y = np.array([], dtype=np.int16)
    y_noise = np.array([], dtype=np.int16)

    try:
        for frame in collected_frames:
            if frame is not None:
                if not triggered_1:
                    # first yield is the list of buffered frames from just before speech started
                    if spinner: spinner.start()
                    y = np.concatenate([np.frombuffer(f, np.int16) for f in frame])
                    y_noise = np.concatenate([np.frombuffer(f, np.int16) for f in frame])
                    triggered_1 = True
                else:
                    # then single frames until the speaker stops
                    if isinstance(frame, bytes):
                        y_dummy = np.frombuffer(frame, np.int16)
                        y = np.concatenate((y, y_dummy))

            if frame is None:
                if spinner: spinner.stop()

                if y.size > 0 and y_noise.size > 0:
                    triggered_1 = False
                    # whole utterance is denoised in one go, then fed to DeepSpeech
                    reduced_noise_speech = nr.reduce_noise(y=y, y_noise=y_noise, sr=16000, thresh_n_mult_nonstationary = 1, n_std_thresh_stationary = 0.9)
                    reduced_noise_speech_bytes = reduced_noise_speech.astype(np.int16).tobytes()
                    stream_context.feedAudioContent(np.frombuffer(reduced_noise_speech_bytes, np.int16))
                    if ARGS.savewav:
                        wav_data.extend(reduced_noise_speech_bytes)
                y = np.array([], dtype=np.int16)
                y_noise = np.array([], dtype=np.int16)

                if ARGS.savewav:
                    vad_audio.write_wav(os.path.join(ARGS.savewav, datetime.now().strftime("savewav_%Y-%m-%d_%H-%M-%S_%f.wav")), wav_data)
                    wav_data = bytearray()
                text = stream_context.finishStream()
                print("Recognized: %s" % text)

                morse_message = translate(text)
                print(morse_message)
                for char in morse_message.split(' '):
                    transmit_morse(char)

                print("Done transmitting, waiting 5 seconds")
                time.sleep(5)

                stream_context = model.createStream()
    finally:
        GPIO.cleanup()


if __name__ == '__main__':
    DEFAULT_SAMPLE_RATE = 16000

    import argparse
    parser = argparse.ArgumentParser(description="Stream from microphone to DeepSpeech using VAD, then send it as Morse over the laser")

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
