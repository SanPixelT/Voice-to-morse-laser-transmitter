# Step 1: resample LJ Speech clips from 22.05 kHz to 16 kHz (what DeepSpeech and webrtcvad expect).
# Download LJ Speech 1.1 from https://keithito.com/LJ-Speech-Dataset/ and unzip it into data/.

import os
from scipy.signal import resample
import soundfile as sf

# Function to resample audio
def resample_audio(input_file, output_file, target_rate=16000):
    # Read audio file
    audio_data, original_rate = sf.read(input_file)

    # Resample audio data
    resampled_audio = resample(audio_data, int(len(audio_data) * target_rate / original_rate))

    # Save resampled audio to new file
    sf.write(output_file, resampled_audio, target_rate)

# Directory paths
input_dir = os.path.join("data", "LJSpeech-1.1", "wavs")
output_dir = os.path.join("data", "LJSpeech-1.1_resampled", "wavs")

# Create output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Iterate through all WAV files from LJ001-0001.wav to LJ001-0186.wav
for i in range(1, 187):  # Range goes up to 187 exclusive
    input_file = os.path.join(input_dir, f"LJ001-{i:04d}.wav")
    output_file = os.path.join(output_dir, f"LJ001-{i:04d}_resampled.wav")

    # Resample audio
    resample_audio(input_file, output_file)

    print(f"Resampled {input_file} and saved to {output_file}")
