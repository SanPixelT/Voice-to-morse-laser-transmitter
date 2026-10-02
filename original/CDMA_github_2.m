close all;
clc;

text = 'ho';
data = textToBinaryMorse(text);
disp('Binary Morse Code:');
disp(data);


fs = 10000; % Sampling frequency
Tb = 0.06; % Time for one bit (dot duration) in seconds
fc = 550; % Carrier frequency for OOK

% Generate message signal using rectpulse
msg = rectpulse(data, Tb*fs);

% Time vector for the entire message signal
t = (0:length(msg)-1)/fs;

% Generate carrier sine wave
carrier = sin(2*pi*fc*t);

% OOK Modulation
ook_data = msg .* carrier;

% Plotting
figure('Name','OOK Modulation with Sine Wave','NumberTitle','off')
subplot(3,1,1);
plot(rectpulse(data,Tb*fs)); 
axis([0 length(rectpulse(data,Tb*fs)) -0.2 1.2]);
title('Message Signal');
xlabel('n');
ylabel('Binary');
grid on;

subplot(3,1,3);
plot(t(1:2000), ook_data(1:2000)); % Plot first part to visualize
axis([0 t(2100) -1.2 1.2]);
title('OOK Modulated Signal (zoomed)');
xlabel('Time (s)');
ylabel('Amplitude');
grid on;

subplot(3,1,2);
plot(t, ook_data); % Plot first part to visualize
axis([0 t(end) -1.2 1.2]);
title('OOK Modulated Signal');
xlabel('Time (s)');
ylabel('Amplitude');
grid on;

figure
fft_ook = fft(ook_data);
P2 = abs(fft_ook/length(ook_data));
P1 = P2(1:length(ook_data)/2+1);
P1(2:end-1) = 2*P1(2:end-1);
f = fs*(0:(length(ook_data)/2))/length(ook_data);
plot(f, P1);
title('FFT of OOK Signal');
xlabel('Frequency (Hz)');
ylabel('|P1(f)|');
grid on;

P1_OOK = P1;


length_data = length(data);  % Length of the original data
msg = rectpulse(data, Tb*fs);  % Upsample the Morse code data

% Generate PN sequence 
sr=[1 -1 1 -1];  
pn1=[];
for i=1:length_data
    for j=1:200  % Assuming each bit of PN is repeated 10 times
        pn1=[pn1 sr(4)];  
        if sr(4)==sr(3)
            temp=-1;
        else
            temp=1;
        end
        sr=[temp, sr(1:3)];  % Shift the register
    end
end


% Upsample PN sequence to match the message signal's sampling rate
pnUpsampled = repelem(pn1, Tb*fs/200);  % Adjust upsampling to match msg

% Time vector for the entire message signal
t = (0:length(msg)-1)/fs;

% Plot the PN code
figure; 
plot(t(1:2000), pnUpsampled(1:2000))
xlabel('Time (s)');
ylabel('Amplitude');
title('PN code generated from LFSR');
axis([0 t(2100) -1.2 1.2]);
grid on;

% Generate carrier sine wave for OOK modulation
carrier = sin(2*pi*550*t);

% OOK Modulation using the binary data and carrier
ookSignal = msg .* carrier;

% Apply DSSS using the upsampled PN sequence
dsssSignal = ookSignal .* pnUpsampled;

% Add noise to the DSSS signal
sigtonoise = 20;  % SNR in dB
compositeSignal = awgn(dsssSignal, sigtonoise, 'measured');
%compositeSignal = dsssSignal

% Plotting
figure('Name','DSSS Signal','NumberTitle','off');
 subplot(3,1,1);

plot(t, dsssSignal);
xlabel('Time (s)');
ylabel('Amplitude');
title('Transmitted Signal');
axis([0 t(end) -1.2 1.2]);
grid on;

subplot(3,1,2);
plot(t, compositeSignal);
title('Transmitted with AWGN Noise, SNR = 20 dB (Composite Signal)');
xlabel('Time (s)');
ylabel('Amplitude');

axis([0 t(end) -1.2 1.2]);
grid on;

subplot(3,1,3);
plot(t(1:2000), compositeSignal(1:2000)); % Plot first part to visualize
axis([0 t(2100) -1.2 1.2]);
title('Composite Signal (zoomed)');
xlabel('Time (s)');
ylabel('Amplitude');
grid on;

figure
fftSignal = fft(compositeSignal);
P2 = abs(fftSignal/length(compositeSignal));
P1 = P2(1:length(compositeSignal)/2+1);
P1(2:end-1) = 2*P1(2:end-1);
f = fs*(0:(length(compositeSignal)/2))/length(compositeSignal);
plot(f, P1);
title('FFT of Composite Signal');
xlabel('Frequency (Hz)');
ylabel('|P1(f)|');
grid on;

% Compute Power Spectrum in dB for DSSS
powerSpectrum_dB = 10 * log10(P1.^2);

% Plot Power Spectrum
figure;
plot(f, powerSpectrum_dB);
title('Power Spectrum of Composite Signal and OOK Signal');
xlabel('Frequency (Hz)');
ylabel('Power/Frequency (dB/Hz)');
grid on;
hold on; 

% Compute Power Spectrum in dB for OOK
powerSpectrum_dB_OOK = 10 * log10(P1_OOK.^2);

% Plot Power Spectrum
plot(f, powerSpectrum_dB_OOK);
axis([0 f(end) -100 0]);
legend('Spread Spectrum Signal (DSSS)','Message Signal (OOK)')





function data = textToBinaryMorse(text)
    % Mapping from characters to Morse code
    morseMap = containers.Map({'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', ...
                               'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', ...
                               'U', 'V', 'W', 'X', 'Y', 'Z', '1', '2', '3', '4', ...
                               '5', '6', '7', '8', '9', '0', ' '}, ...
                              {'.-', '-...', '-.-.', '-..', '.', '..-.', '--.', '....', '..', '.---', ...
                               '-.-', '.-..', '--', '-.', '---', '.--.', '--.-', '.-.', '...', '-', ...
                               '..-', '...-', '.--', '-..-', '-.--', '--..', '.----', '..---', '...--', '....-', ...
                               '.....', '-....', '--...', '---..', '----.', '-----', '/'});
    
    % Convert the text to uppercase
    textUpper = upper(text);
    
    % Initialize the binary Morse code data as an empty array
    data = [];
    
    % Convert each character to Morse code and then to binary
    for i = 1:length(textUpper)
        if morseMap.isKey(textUpper(i))
            morseCode = morseMap(textUpper(i));
            % Convert Morse code to binary
            for j = 1:length(morseCode)
                switch morseCode(j)
                    case '.'
                        data = [data, 1];  % Dot
                    case '-'
                        data = [data, 1, 1, 1];  % Dash
                end
                if j < length(morseCode)
                    data = [data, 0];  % Inter-character space within a letter
                end
            end
        else
            continue;  % Skip unsupported characters
        end
        if i < length(textUpper)
            if textUpper(i) == ' '  % Inter-word space
                data = [data, 0, 0, 0];
            else
                data = [data, 0];  % Inter-character space
            end
        end
    end
end

