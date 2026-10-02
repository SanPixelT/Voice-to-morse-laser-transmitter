import os
import numpy as np
import soundfile as sf
import matplotlib.pyplot as plt
import noisereduce as nr

# Function to add noise to audio
def add_noise(audio_data, noise_level=0.1):
    noise = np.random.normal(scale=noise_level, size=len(audio_data))
    noisy_audio = audio_data + noise
    noisy_audio = np.clip(noisy_audio, -1.0, 1.0)  # Normalize to ensure the audio remains within [-1, 1]
    return noisy_audio

def print_noise_levels(original_audio, noisy_audio):
    original_std = np.std(original_audio)
    noisy_std = np.std(noisy_audio)
    print(f"Standard Deviation of Original Audio: {original_std:.5f}")
    print(f"Standard Deviation of Noisy Audio: {noisy_std:.5f}")

# Directory paths
input_dir = "C:\\Users\\alief\\Downloads\\LJSpeech-1.1_resampled\\wavs"
output_dir = "C:\\Users\\alief\\Downloads\\LJSpeech-1.1_noise\\wavs"
os.makedirs(output_dir, exist_ok=True)  # Ensure the output directory exists

noise_level = 0.025  # Noise level

# Create an iterator from the list of filenames in the input directory and get the first file
filename_iterator = iter(os.listdir(input_dir))
filename = next(filename_iterator)
input_file = os.path.join(input_dir, filename)
output_file = os.path.join(output_dir, filename)

# Read the resampled audio file
audio_data, samplerate = sf.read(input_file)

# Add noise to the audio
noisy_audio = add_noise(audio_data, noise_level=noise_level)

# Simulate a "noise reduction" process for demonstration purposes
reduced_noise_non = nr.reduce_noise(y=noisy_audio, sr=16000, thresh_n_mult_nonstationary=0.3,stationary=False) 
reduced_noise = nr.reduce_noise(y=noisy_audio, y_noise = np.random.normal(scale=noise_level, size=len(audio_data)),sr=16000)


# Save the noisy audio to a new file
sf.write(output_file, noisy_audio, samplerate)

# Print the noise levels (standard deviation) before and after adding noise
print_noise_levels(audio_data, noisy_audio)

# Create and save a figure with three subplots
plt.figure(figsize=(12, 8))

plt.subplot(4, 1, 1)
plt.plot(audio_data)
plt.title("Audio (Original)")
plt.xlabel("Sample")
plt.ylabel("Amplitude")
plt.grid(which='major', linestyle='--', linewidth=1)

plt.subplot(4, 1, 2)
plt.plot(noisy_audio)
plt.title("Audio with Added Noise")
plt.xlabel("Sample")
plt.ylabel("Amplitude")
plt.grid(which='major', linestyle='--', linewidth=1)

plt.subplot(4, 1, 3)
plt.plot(reduced_noise)
plt.title("Audio After Noise Reduction (Stationary)")
plt.xlabel("Sample")
plt.ylabel("Amplitude")
plt.grid(which='major', linestyle='--', linewidth=1)

plt.subplot(4, 1, 4)
plt.plot(reduced_noise_non)
plt.title("Audio After Noise Reduction (Non-Stationary)")
plt.xlabel("Sample")
plt.ylabel("Amplitude")
plt.grid(which='major', linestyle='--', linewidth=1)

plt.tight_layout()
plt.savefig("output_figure.png")  # Save the figure to a file
plt.show()  # Display the figure

print(f"Noisy audio saved to {output_file}")
