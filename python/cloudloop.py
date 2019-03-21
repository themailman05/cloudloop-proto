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
import multiprocessing

CHUNK = 2048
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
            print(f'callback for click {input_data} {frame_count} {time_info} {status}')
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
    def __init__(self, input_channel=0, output_channel=0, sample_rate=48000):
        self.framebuffer=[]
        self.input_channel = input_channel
        self.sample_rate = sample_rate
        self.loop_ready = False
        def record_callback(input_data, frame_count, time_info, status):
            print(f'callback for recording {frame_count} {time_info} {status}')
            self.framebuffer.append(input_data)
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
        record_time = (60/bpm)*(beats_per_measure * measures)
        print(f"Recording for {record_time}")
        start_time = time.time_ns()
        start_time_seconds = time.time_ns() / (10**9)
        self.input_stream.start_stream()
        recording = True
        while (recording):
            time.sleep(.01)
            recording = (time.time_ns() / (10**9) - start_time_seconds) < 0
        self.input_stream.stop_stream()
        self.loop = Loop(framebuffer = self.framebuffer)
        self.loop.dump()
        self.loop_ready = True
        stop_time = time.time_ns()
        recorded_time = stop_time - start_time
        print(f"Done recording: {recorded_time}ns")

    def play(self, loops=1):
        if (not self.loop_ready):
            print("Can't play; Record something first")
        else:
            frameGen = self.loop.frame_generator()
            print('Playing loop.')
            def playback_callback(input_data, frame_count, time_info, status):
                print(f'callback for stream playback {frame_count} {time_info} {status}')
                data = frameGen.__next__()
                print(data)
                return data, pyaudio.paContinue
            self.output_stream = p.open(format=FORMAT,
                                        channels=CHANNELS,
                                        rate=sample_rate,
                                        output_device_index=output_channel,
                                        input=False,
                                        output=True,
                                        frames_per_buffer=CHUNK,
                                        stream_callback=playback_callback)
            for i in range(loops):
                self.output_stream.start_stream()
                while (self.output_stream.is_active()):
                    time.sleep(.001)
                self.output_stream.stop_stream()


class Loop:
    def __init__(self, track_name='newTrack', framebuffer=[], sample_rate=48000, channels=CHANNELS):
        self.track_name=track_name
        self.framebuffer = framebuffer
        self.sample_rate = sample_rate
        self.num_frame_chunks = len(framebuffer)
        self.channels = channels
        self.current_frame_chunk = 0
    def frame_generator(self):
        print(self.num_frame_chunks)
        if (self.current_frame_chunk < self.num_frame_chunks):
            yield self.framebuffer[self.current_frame_chunk]
            self.current_frame_chunk += 1
    def dump(self, file_name='recording.wav'):
        wav_bytes = b''.join(self.framebuffer)
        print(type(wav_bytes))
        with wave.open(file_name, 'wb') as f:
            f.setframerate(self.sample_rate)
            f.setsampwidth(3) #24 bit = 3 bytes
            f.setnchannels(self.channels)
            f.setnframes(CHUNK*len(self.framebuffer))
            wav_format = p.get_format_from_width(f.getsampwidth())
            f.writeframes(wav_bytes)



input_channel, output_channel, sample_rate = configure('macbookpro')

audio_track = AudioTrack(input_channel=input_channel, output_channel=output_channel)
click_track = ClickTrack(click_sound_file='metsound.wav', output_channel=output_channel)

click_thread = multiprocessing.Process(target=click_track.play(160,4,1))
audio_thread = multiprocessing.Process(target=audio_track.record(160,4,1))

audio_thread.start()
click_thread.start()
click_thread.join()
audio_thread.join()

audio_playback_thread = multiprocessing.Process(target=audio_track.play(1))
audio_playback_thread.start()
audio_playback_thread.join()



#frames = loop_record(click=True, bpm=100.0, input_channel=input_channel, output_channel=output_channel, sample_rate=sample_rate)
#loop_play(frames, cycles=4, input_channel=input_channel, output_channel=output_channel, sample_rate=sample_rate)

p.terminate()
