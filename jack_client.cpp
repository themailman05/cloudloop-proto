#include <unistd.h>
#include <iostream>
#include <jack/jack.h>
#include <jack/ringbuffer.h>
#include <signal.h>
#include <sndfile.h>
#include <stdio.h>
#include <stdlib.h>
#include <malloc.h>

using namespace std;

jack_port_t **inputPortArray;
jack_default_audio_sample_t **inputBufferArray;
// global ringbuffer ptr (move to class)
jack_ringbuffer_t *buffer = 0;

int running;
pthread_mutex_t threadLock = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t dataReady = PTHREAD_COND_INITIALIZER;

int write(int i)
{
  // get free space
  int availableWrite = jack_ringbuffer_write_space(buffer);

  if (availableWrite >= sizeof(int))
  {
    //write data, keep track of what was written
    int written = jack_ringbuffer_write( buffer, (const char*) &i, sizeof(int) );
    if (written != sizeof(int) ) {
      std::cout << "ERROR didn't write full int" << std::endl;
    }
  }
  else {
    std::cout << "ERROR ringbuff full, skipping" << std::endl;
  }
}

int process(jack_nframes_t nframes, void* arg)
{
  // check if there's anything to read
  int availableRead = jack_ringbuffer_read_space(buffer);
  int portNum;
  jack_nframes_t frameNum;

  for (portNum=0; portNum<NUM_INPUT_PORTS ; portNum++)
  {
       inputBufferArray[portNum] = jack_port_get_buffer(inputPortArray[portNum], nframes);
  }

  // Iterate through input buffers, adding samples to ring buffer
  for (frameNum=0; frameNum<nframes; frameNum++)
  {
      for (portNum=0; portNum<NUM_INPUT_PORTS; portNum++)
      {
          size_t written = jack_ringbuffer_write(buffer, (void *) &inputBufferArray[portNum][frameNum], sizeof(jack_default_audio_sample_t));
          if (written != sizeof(jack_default_audio_sample_t))
          {
              printf("Ringbuffer overrun\n");
          }
      }
  }
  
  // Attempt to lock threadLock mutex, returns zero if lock acquired
  if (pthread_mutex_tryLock(&threadLock) == 0)
  {
        // Wake up thread waiting on condition (should only be called after lock acq'd)
        pthread_cond_signal(&dataReady);
        pthread_mutex_unlock(&threadLock);
  }
  return 0;
}

  if ( availableRead >= sizeof(int) )
  {
    int tempInt; // to read val

    int result = jack_ringbuffer_read(buffer, (char*) &tempInt, sizeof(int));

    if ( result != sizeof(int) ) {
      std::cout << "RtQueue::pull() WARNING! didn't read full event!" << std::endl;
      return -1;
    }

    std::cout << "Jack says int = " << tempInt << std::endl;
  }

  return 0;
}

int main ()
{
  std::cout << "Ring buffer tutorial" << std::endl;
  
  // create an instance of a ringbuffer that will hold up to 20 integers,
  // let the pointer point to it
  buffer = jack_ringbuffer_create( 20 * sizeof(int));
  
  // lock the buffer into memory, this is *NOT* realtime safe, do it before
  // using the buffer!
  int res = jack_ringbuffer_mlock(buffer);
  
  // check if we've locked the memory successfully
  if ( res ) {
    std::cout << "Error locking memory!" << std::endl;
    return -1;
  }
  
  // create a JACK client, register the process callback and activate
  jack_client_t* client = jack_client_open ( "RingbufferDemo", JackNullOption , 0 , 0 );
  jack_set_process_callback  (client, process , 0);
  jack_activate(client);
  
  for ( int i = 0; i < 1000; i++)
  {
    // write an event, then pause a while, JACK will get a go and then
    // we'll write another event... etc
    write(i);
    usleep(1000000);
  }
  
  
  return 0;
}
