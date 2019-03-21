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
import pprint
import time
from multiprocessing import Process, Pipe
import io
import termios, sys

CHUNK = 512
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
LOOP_TIME = 3
WAVE_OUTPUT_FILENAME = "output.wav"
CLICK_SOUND = "metsound.wav"


p = pyaudio.PyAudio()

def configure(mode='auto'):
    dev_count = p.get_device_count()
    info_by_channel = [ p.get_device_info_by_index(x) for x in range(dev_count) ]
    pprint.pprint(info_by_channel)

    for device in info_by_channel:
        if mode == 'macbookpro':
            if device['name'] == 'MacBook Pro Microphone':
                input_channel = device['index']
                sample_rate = int(device['defaultSampleRate'])
            if device['name'] == 'MacBook Pro Speakers':
                output_channel = device['index']
        elif mode == 'auto':
            if (device['maxInputChannels'] > 0 and not input_channel):
                input_channel = device['index']
            if (device['maxOutputChannels'] > 0 and not output_channel):
                output_channel = device['index']
    print(f'Input Channel: {input_channel}')
    print(f'Output Channel: {output_channel}')
    return (input_channel, output_channel, sample_rate)

class ClickTrack:
    'Click Track'
    def __init__(self, click_sound_file='metsound.wav', output_channel=0, buffer_size=CHUNK):
        self.click_sound_file = click_sound_file
        self.click_wav = wave.open(self.click_sound_file)
        self.click_sample_rate = self.click_wav.getframerate()
        self.click_sample_width = self.click_wav.getsampwidth()
        self.click_samples = self.click_wav.getnframes()
        self.click_format = p.get_format_from_width(self.click_wav.getsampwidth())
        self.buffer_size = buffer_size
        self.click_wav_channels = self.click_wav.getnchannels()
        self.output_channel = output_channel
        def click_callback(input_data, frame_count, time_info, status):
            print(f'* click {input_data} {frame_count} {time_info} {status}')
            data = self.click_wav.readframes(frame_count)
            return data, pyaudio.paContinue
        print(f"Using {self.click_sound_file}:{self.click_sample_rate};{self.click_wav_channels} for metronome on {self.output_channel}; {self.click_samples} samples in click")
        self.click_stream = p.open(format=self.click_format,
                                   channels=self.click_wav_channels,
                                   rate=self.click_sample_rate,
                                   output=True,
                                   output_device_index=output_channel,
                                   frames_per_buffer=CHUNK,
                                   stream_callback=click_callback)

    def play(self, bpm, beats_per_measure, measures):
        print(f'sample width: {self.click_sample_width}')
        print(f"Playing click at {bpm} for {measures} of {beats_per_measure}")
        click_delay_seconds = 60.0/bpm
        print(f"Seconds per click: {click_delay_seconds}")
        loops = 0
        start_time = time.time_ns()
        start_time_seconds = time.time_ns() / (10**9)
        while loops < (beats_per_measure * measures):
            self.click_play()
            time.sleep(click_delay_seconds)
            loops+=1
    def reset_wav(self):
        self.click_wav.rewind()
    def click_play(self):
        self.click_stream.start_stream()
        while(self.click_stream.is_active()):
            time.sleep(.0001)
            #poll for changes here? how to not waste cycles?
        self.reset_wav()
        self.click_stream.stop_stream()


class AudioTrack:
    'Audio Input Track'
    def __init__(self, input_channel=0, output_channel=0, sample_rate=48000, track_number=1):
        self.input_channel = input_channel
        self.sample_rate = sample_rate
        self.track_number = track_number
        self.loop = Loop(f'{self.track_number}')
        self.recording = False
        def record_callback(input_data, frame_count, time_info, status):
            print(f'* recording {frame_count} {time_info} {status}')
            self.loop.framebuffer.append(input_data)
            return input_data, pyaudio.paContinue
        self.input_stream = p.open(format=FORMAT,
                             channels=CHANNELS,
                             rate=self.sample_rate,
                             input=True,
                             output=False,
                             input_device_index=input_channel,
                             frames_per_buffer=CHUNK,
                             stream_callback=record_callback)
    def record(self, bpm, beats_per_measure, measures):
        record_time = (60/bpm) * (beats_per_measure * measures)
        print(f"Recording for {record_time}")
        start_time = time.time_ns()
        start_time_seconds = time.time_ns() / (10**9)
        self.input_stream.start_stream()
        self.loop.disarm()
        self.recording = True
        while (self.recording):
            time.sleep(.01)
            self.recording = (time.time_ns() / (10**9) - start_time_seconds) < 0
        self.input_stream.stop_stream()
        self.loop.ready()
        stop_time = time.time_ns()
        recorded_time = stop_time - start_time
        print(f"Done recording: {recorded_time}ns")

    def play(self, nloops=1):
        if (not self.loop.play_ready):
            print("Can't play; Record something first")
        else:
            frameGen = self.loop.frame_generator(nloops)
            def playback_callback(input_data, frame_count, time_info, status):
                print(f'* playback {frame_count} {time_info} {status}')
                data = next(frameGen)
                return data, pyaudio.paContinue
            self.output_stream = p.open(format=FORMAT,
                                    channels=CHANNELS,
                                    rate=sample_rate,
                                    output_device_index=output_channel,
                                    input=False,
                                    output=True,
                                    frames_per_buffer=CHUNK,
                                    stream_callback=playback_callback)
            self.output_stream.start_stream()
            while (self.output_stream.is_active()):
                time.sleep(.001)
            self.output_stream.stop_stream()


class Loop:
    def __init__(self, track_name='newTrack', framebuffer=[], sample_rate=48000, sample_width=3, channels=CHANNELS, chunk=CHUNK):
        self.track_name=track_name
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels
        self.chunk = chunk
        self.framebuffer = []
        self.play_ready = False
    def ready(self):
        self.play_ready = True
    def disarm(self):
        self.play_ready = False
    def frame_generator(self, nloops=1, current_frame=0):
        loop_frame_count = len(self.framebuffer)
        frames_to_generate = loop_frame_count * nloops
        while (current_frame < frames_to_generate):
            yield self.framebuffer[current_frame % loop_frame_count]
            current_frame += 1
        yield None
    def dump(self, file_name='recording.wav'): #broken
        wav_bytes = b''.join(self.framebuffer)
        with wave.open(file_name, 'wb') as f:
            f.setframerate(self.sample_rate)
            f.setsampwidth(self.sample_width) #24 bit = 3 bytes
            f.setnchannels(self.channels)
            f.setnframes(CHUNK*len(self.framebuffer))
            wav_format = p.get_format_from_width(f.getsampwidth())
            f.writeframes(wav_bytes)
    def clear(self):
        self.framebuffer = 0

class CloudLoop:
    def __init__(self, configuration='macbookpro'):
        self.session = Session(configuration)
    def begin_session(self):
        self.session.create_track()



class Session:
    def __init__(self, configuration='macbookpro', bpm=bpm, beats_per_measure=4, measures=2:
        self.input_channel, self.output_channel, self.sample_rate = configure(configuration)
        self.tracks = []
        click_track = ClickTrack(self.output_channel)
        self.tracks.append(click_track)
        self.bpm = bpm
        self.beats_per_measure = beats_per_measure
        self.measures = measures
        self.audio_processes = []
    def create_track(self):
        track_number = len(self.tracks)
        self.tracks.append(AudioTrack(self.input_channel, self.output_channel, self.sample_rate, track_number=track_number))
    def record_loop(self, track_number, click=True):
        self.audio_processes.add(self.tracks[track_number].record(self.bpm, self.beats_per_measure, self.measures))
        if (click):
            self.audio_processes.add(self.tracks[0].play(self.bpm, self.beat_per_measure, self.measures))
        map(lambda p: p.start(), self.audio_processes)
        map(lambda j: j.join(), self.audio_processes)

    def play_track(self, track_number, nloops=1):
        if (track_number <= len(self.tracks)+1):
            self.tracks[track_number].play(nloops)

        
    

input_channel, output_channel, sample_rate = configure('macbookpro')

audio_track = AudioTrack(input_channel=input_channel, output_channel=output_channel)
click_track = ClickTrack(click_sound_file='metsound.wav', output_channel=output_channel)
click_thread = multiprocessing.Process(target=click_track.play(160,4,1))
audio_thread = multiprocessing.Process(target=audio_track.record(160,4,1))

audio_thread.start()
click_thread.start()
click_thread.join()
audio_thread.join()

audio_playback_thread = multiprocessing.Process(target=audio_track.play(4))
audio_playback_thread.start()
audio_playback_thread.join()


#frames = loop_record(click=True, bpm=100.0, input_channel=input_channel, output_channel=output_channel, sample_rate=sample_rate)
#loop_play(frames, cycles=4, input_channel=input_channel, output_channel=output_channel, sample_rate=sample_rate)

p.terminate()
