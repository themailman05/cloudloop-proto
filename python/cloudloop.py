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
from threading import Thread
import io
import termios, sys
from decimal import *
import asyncio

CHUNK = 128
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

class ClickTrack(Thread):
    'Click Track'
    def __init__(self, click_sound_file='metsound.wav', output_channel=0, buffer_size=CHUNK, countin=True):
        super(ClickTrack, self).__init__()
        self.click_sound_file = click_sound_file
        self.click_wav = wave.open(self.click_sound_file)
        self.click_sample_rate = self.click_wav.getframerate()
        self.click_sample_width = self.click_wav.getsampwidth()
        self.click_samples = self.click_wav.getnframes()
        self.click_format = p.get_format_from_width(self.click_wav.getsampwidth())
        self.buffer_size = buffer_size
        self.click_wav_channels = self.click_wav.getnchannels()
        self.ready = False
        self.output_channel = output_channel
        if (countin):
            self.measures = 1
        else:
            self.measures = 4
        self.start()
    def arm_stream(self):
        print(f"Using {self.click_sound_file}:{self.click_sample_rate};{self.click_wav_channels} for metronome on {self.output_channel}; {self.click_samples} samples in click")
        self.click_stream = p.open(format=self.click_format,
                                   channels=self.click_wav_channels,
                                   rate=self.click_sample_rate,
                                   output=True,
                                   output_device_index=self.output_channel,
                                   frames_per_buffer=CHUNK)
        self.ready = True
    def play(self, bpm, beats_per_measure, measures):
        print(f'sample width: {self.click_sample_width}')
        print(f"Playing click at {bpm} for {measures} of {beats_per_measure}")
        click_delay_seconds = 60.0/bpm
        print(f"Seconds per click: {click_delay_seconds}")
        loops = 0
        start_time = time.time_ns()
        start_time_seconds = time.time_ns() / (10**9)
        self.arm_stream()
        while loops < (beats_per_measure * measures):
            self.click_play()
            time.sleep(click_delay_seconds)
            loops+=1
    def reset_wav(self):
        self.click_wav.rewind()
    def click_play(self):
        self.click_stream.write(self.click_wav.readframes(1000))
        print('click')
        self.reset_wav()
    def run(self):
        self.play(120,4,self.measures)

class AudioOutputTrack(Thread):
    'Audio Track'
    def __init__(self, output_channel=0, sample_rate=48000, track_number=1, loop=None, nloops=2):
        super(AudioOutputTrack, self).__init__()
        self.output_channel = output_channel
        self.sample_rate = sample_rate
        self.track_number = track_number
        self.loop = loop
        self.start()
        self.frameGen = self.loop.frame_generator(nloops)
    def playback_callback(self, input_data, frame_count, time_info, status):
        #print(f'* playback {frame_count} {time_info} {status}')
        data = next(self.frameGen)
        return data, pyaudio.paContinue
    def arm_stream(self):
        self.output_stream = p.open(format=FORMAT,
                                    channels=CHANNELS,
                                    rate=self.sample_rate,
                                    output_device_index=self.output_channel,
                                    input=False,
                                    output=True,
                                    frames_per_buffer=CHUNK,
                                    stream_callback=self.playback_callback)
    def play(self, nloops=1):
        if (not self.loop.play_ready):
            print("Can't play; Record something first")
        else:
            self.arm_stream()
            self.output_stream.start_stream()
            while (self.output_stream.is_active()):
                time.sleep(.001)
            self.output_stream.stop_stream()
    def run(self):
        self.play(2)


class AudioInputTrack(Thread):
    'Audio Track'
    def __init__(self, input_channel=0, output_channel=0, sample_rate=48000, track_number=1):
        super(AudioInputTrack, self).__init__()
        self.input_channel = input_channel
        self.output_channel = output_channel
        self.sample_rate = sample_rate
        self.track_number = track_number
        self.loop = Loop(f'{self.track_number}')
        self.recording = False
        self.start()
    def record_callback(self, input_data, frame_count, time_info, status):
            #print(f'* recording {frame_count} {time_info} {status}')
            self.loop.framebuffer.append(input_data)
            return input_data, pyaudio.paContinue
    def arm_stream(self):
        self.input_stream = p.open(format=FORMAT,
                             channels=CHANNELS,
                             rate=self.sample_rate,
                             input=True,
                             output=False,
                             input_device_index=self.input_channel,
                             frames_per_buffer=CHUNK,
                             stream_callback=self.record_callback)
    def record(self, bpm, beats_per_measure, measures):
        record_time = (60/bpm) * (beats_per_measure * measures)
        print(f"Recording for {record_time}")
        start_time = time.time_ns()
        start_time_seconds = time.time_ns() / (10**9)
        print(f'{start_time_seconds}')
        self.arm_stream()
        self.input_stream.start_stream()
        self.loop.disarm()
        self.recording = True
        while (self.recording):
            time.sleep(.001)
            self.recording = (time.time_ns() / (10**9) - start_time_seconds) < record_time
        self.input_stream.stop_stream()
        self.loop.ready()
        stop_time = time.time_ns()
        recorded_time = stop_time - start_time
        print(f"Done recording: {recorded_time}ns")
    def run(self):
        self.record(120,4,4)

    


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

class Clock(Thread):
    def __init__(self, bpm=120, num_beats=8):
        self.start_time = time.perf_counter_ns()
        self.beat_time_s = 60.0 / bpm
        self.beat_time_ns = self.beat_time_s * (10**9)
        print(f'{self.beat_time_ns} nanoseconds per beat')
        self.num_beats = num_beats
        self.beat_points_ns = [ (self.start_time + (self.beat_time_ns * beat)) for beat in range(num_beats+12) ]
        print(f"Clock start {self.start_time} : {self.beat_time_s}s per beat. {self.beat_time_ns}")
        print(f'\n\n{self.beat_points_ns}\n')
        print(list(map(lambda x: x-self.start_time, self.beat_points_ns)))
    async def clock_loop(self, num=0, precision=0.001, error_ns=400000, stable_error=True):
        next_beat = self.start_time + self.beat_time_ns
        next_beat_with_error = self.start_time + (self.beat_time_ns - error_ns)
        sleeps = [0] * num
        actual_errors = []
        abs_errors = []
        clock_errors = []
        while len(actual_errors) < num:
            sleeps[len(actual_errors)] += 1
            await asyncio.sleep(precision)
            now = time.perf_counter_ns()
            if now > next_beat_with_error:
                clock_error = now - next_beat_with_error
                actual_error = now - next_beat
                abs_error = abs(actual_error)
                clock_errors.append(clock_error)
                abs_errors.append(abs_error)
                actual_errors.append(actual_error)
                if stable_error:
                    next_beat_with_error = (next_beat + self.beat_time_ns) - error_ns
                else:
                    next_beat_with_error = (next_beat + (self.beat_time_ns)) - (actual_error/2)
                next_beat = next_beat + self.beat_time_ns
        return (sleeps, actual_errors, clock_errors)
        
async def main():
    input_channel, output_channel, samplerate = configure('macbookpro')
    print('ok!')
    results = []
    for i in range(10):
        clock = Clock()
        task = asyncio.create_task(clock.clock_loop(8, 0.001, stable_error=False))
        await task
        results.append(task.result())

    final_results = []
    for i in range(10):
        actual_error, sleeps, clock_error = results[i]
        average_actual_error = sum(actual_error) / len(actual_error)
        average_sleeps = sum(sleeps) / len(sleeps)
        average_clock_error = sum(clock_error) / len(clock_error)
        final_results.append(average_actual_error, average_sleeps, average_clock_error)
        print(f'\n\naverage of {i} trial: \nactual error: {average_actual_error}\nclock error(latency): {average_clock_error} \nsleeps: {average_sleeps}')

if __name__ == '__main__':
    asyncio.run(main())


"""
click_in = ClickTrack(click_sound_file='metsound.wav', output_channel=output_channel,countin=True)
click_in.join()
track_1 = AudioInputTrack(input_channel, output_channel, samplerate)
click_rec = ClickTrack(click_sound_file='metsound.wav', output_channel=output_channel, countin=False)

track_1.join()
click_rec.join()

playback_track = AudioOutputTrack(output_channel=output_channel, sample_rate=samplerate, loop=track_1.loop, nloops=4)
playback_track.join()
"""
