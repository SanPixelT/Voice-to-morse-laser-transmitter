# Step 2: add white Gaussian noise to every resampled clip, to simulate a noisy environment.
# The noisy clips are then run through laptop_test.py with and without noise reduction.

import os
import numpy as np
import soundfile as sf

# Function to add noise to audio
def add_noise(audio_data, noise_level=0.1):
    # Generate random noise with the same length as the audio
    noise = np.random.normal(scale=noise_level, size=len(audio_data))

    # Add noise to audio
    noisy_audio = audio_data + noise

    # Normalize to ensure the audio remains in the valid range [-1, 1]
    noisy_audio = np.clip(noisy_audio, -1.0, 1.0)

    return noisy_audio

# Directory paths
input_dir = os.path.join("data", "LJSpeech-1.1_resampled", "wavs")
output_dir = os.path.join("data", "LJSpeech-1.1_noise", "wavs")

# Create output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Noise level (adjust as needed)
noise_level = 0.025  # standard deviation of the Gaussian noise (audio is in [-1, 1])

# Iterate through all resampled WAV files
for filename in os.listdir(input_dir):
    input_file = os.path.join(input_dir, filename)
    output_file = os.path.join(output_dir, filename)

    # Read resampled audio file
    audio_data, _ = sf.read(input_file)

    # Add noise to audio
    noisy_audio = add_noise(audio_data, noise_level=noise_level)

    # Save noisy audio to new file
    sf.write(output_file, noisy_audio, samplerate=16000)  # Use sample rate 16000 Hz for saving

    print(f"Noisy audio saved to {output_file}")
