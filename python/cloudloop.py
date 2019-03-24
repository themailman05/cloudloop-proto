""" 
CloudLoop POC
(c) Liam Sargent, Zip Technologies LLC 2019
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
import asyncio
from functools import reduce

CHUNK = 256
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

class ClickTrack():
    'Click Track'
    def __init__(self, click_sound_file='metsound.wav', output_channel=0, buffer_size=CHUNK, countin=True, clock=None):
        super(ClickTrack, self).__init__()
        self.clock = clock
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
    def arm_stream(self):
        print(f"Using {self.click_sound_file}:{self.click_sample_rate};{self.click_wav_channels} for metronome on {self.output_channel}; {self.click_samples} samples in click")
        self.click_stream = p.open(format=self.click_format,
                                   channels=self.click_wav_channels,
                                   rate=self.click_sample_rate,
                                   output=True,
                                   output_device_index=self.output_channel,
                                   frames_per_buffer=CHUNK)
        self.ready = True
    async def play(self, bpm, beats_per_measure, measures):
        print(f'sample width: {self.click_sample_width}')
        print(f"Playing click at {bpm} for {measures} of {beats_per_measure}")
        click_delay_seconds = 60.0/bpm
        print(f"Seconds per click: {click_delay_seconds}")
        beats_to_play = beats_per_measure * measures
        self.arm_stream()
        async for beat in self.clock.clock_loop(bpm=bpm):
            print(beat)
            self.click_play()
            if (beat == beats_to_play):
                self.stop()
    def stop(self):
        self.clock.stop()
    def click_play(self):
        self.click_stream.write(self.click_wav.readframes(CHUNK))
        self.click_wav.rewind()
        return

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

class Clock():
    def __init__(self):
        pass
    def stop(self):
        self.running = False
    async def clock_loop(self, bpm=120):
        self.start_time = time.perf_counter_ns()
        self.beat_time_s = 60.0 / bpm
        self.beat_time_ns = self.beat_time_s * (10**9)
        print(f'{self.beat_time_ns} nanoseconds per beat')
        print(f"Clock start {self.start_time} : {self.beat_time_s}s per beat. {self.beat_time_ns}")
        self.beat = 1
        self.running = True
        while self.running:
            await asyncio.sleep(self.beat_time_s)
            #import pdb; pdb.set_trace()
            yield self.beat
            self.beat = self.beat+1
                
async def main():
    input_channel, output_channel, samplerate = configure('macbookpro')
    print('ok!')
    results = []
    clock = Clock()
    click_track = ClickTrack(click_sound_file='metsound.wav', output_channel=output_channel, countin=False, clock=clock)
    await click_track.play(120,4,4)
    print("done")

    """
    for i in range(10):
        clock = Clock()
        task = asyncio.create_task(clock.clock_loop(120, 8, 400000, stable_error=False))
        await results.append(task.result())

    average_average_actual_errors = []
    average_average_sleeps = []
    average_average_clock_errors = []
    for i in range(10):
        sleeps, actual_error, clock_error = results[i]
        average_actual_error = sum(actual_error) / len(actual_error)
        average_sleeps = sum(sleeps) / len(sleeps)
        average_clock_error = sum(clock_error) / len(clock_error)
        average_average_actual_errors.append(average_actual_error)
        average_average_sleeps.append(average_sleeps)
        average_average_clock_errors.append(average_clock_error)
        #print(f'\n\naverage of {i} trial: \nactual error: {average_actual_error}\nclock error(latency): {average_clock_error} \nsleeps: {average_sleeps}')

    final_actual_error = sum(average_average_actual_errors)/len(average_average_actual_errors)
    final_sleeps = sum(average_average_sleeps)/len(average_average_sleeps)
    final_clock_error = sum(average_average_clock_errors)/len(average_average_clock_errors)
    print(f'\nfinal actual error:{final_actual_error}\nfinal actual sleeps: {final_sleeps}\nfinal_clock_error: {final_clock_error}')

"""
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
