""" 
CloudLoop uber-beta
(c) Liam Sargent, 2017
"""

#TODO True looping (add wavs to each other)
#TODO Actual record controls
#TODO Fix buffer underrun issues
#TODO synthesize click
#TODO Actual metronome speed

import pyaudio
import wave

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
LOOP_TIME = 3
WAVE_OUTPUT_FILENAME = "output.wav"
CLICK_SOUND = "metsound.WAV"


p = pyaudio.PyAudio()

def loop_record(click=False, framebuffer=[], beats_per_measure=4, measures=1, bpm=60.0):
    print("* recording")

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    output=True,
                    frames_per_buffer=CHUNK)

    beat_seconds = 60.0/bpm
    measure_seconds = beat_seconds * beats_per_measure
    record_seconds = measure_seconds * measures
    beat_frames = (beat_seconds * RATE)/CHUNK
    print("beat secs: " + str(beat_seconds) + " measure secs: " + str(measure_seconds))
    print("beat frames: " + str(beat_frames))

    if click:
        click_wav = wave.open(CLICK_SOUND)
        click_len = click_wav.getnframes()
        print(str(click_len) + " frames in click")
        click_stream = p.open(format=p.get_format_from_width(click_wav.getsampwidth()),
                              channels=click_wav.getnchannels(),
                              rate=click_wav.getframerate(),
                              output=True)
        print(str(click_wav.getframerate()) + " sample rate")
        click_data = click_wav.readframes(CHUNK)


    for i in range(0, int(RATE / CHUNK * record_seconds)):
        print i
        if i % int(beat_frames) == 0:
            print("CLICK")
            if click:
	        click_stream.write(click_data)
	data = stream.read(CHUNK)
	framebuffer.append(data)
    print("* done recording")

    stream.stop_stream()
    stream.close()

    return framebuffer

print("* begin looping, ctrl+c to stop")

def loop_play(framebuffer, cycles=0):
    loop_time = (float(len(framebuffer))*CHUNK)/RATE

    print(str(loop_time))

    outstream = p.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=RATE,
                       output=True,
                       frames_per_buffer=CHUNK)
    if cycles <= 0:
        while True:
            for i in range(0, int(RATE/CHUNK * loop_time)):
                outstream.write(frames[i], CHUNK)
    else:
        for j in range(0, cycles):
            for i in range(0, int(RATE/CHUNK * loop_time)):
                outstream.write(frames[i], CHUNK)

    outstream.stop_stream()
    outstream.close()


frames = loop_record(click=True, bpm=88.0)
loop_play(frames, cycles=4)

p.terminate()
