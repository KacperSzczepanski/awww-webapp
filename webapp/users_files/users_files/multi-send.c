#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <poll.h>
#include <errno.h>
#include "err.h"

#define BSIZE         256
#define TTL_VALUE     4
#define REPEAT_COUNT  3
#define SLEEP_TIME    1

int main (int argc, char *argv[]) {
  /* argumenty wywołania programu */
  char *remote_dotted_address;
  in_port_t remote_port;

  /* zmienne i struktury opisujące gniazda */
  int optval;
  struct sockaddr_in remote_address;

  /* zmienne obsługujące komunikację */
  char buffer[BSIZE];

  /* parsowanie argumentów programu */
  if (argc != 3)
    fatal("Usage: %s remote_address remote_port\n", argv[0]);

  remote_dotted_address = argv[1];
  remote_port = (in_port_t)atoi(argv[2]);

  struct pollfd client[1];

  client[0].fd = -1;
  client[0].events = POLLIN;
  client[0].revents = 0;

  /* otwarcie gniazda */
  client[0].fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (client[0].fd < 0)
    syserr("socket");

  /* uaktywnienie rozgłaszania (ang. broadcast) */ 
  optval = 1;
  if (setsockopt(client[0].fd, SOL_SOCKET, SO_BROADCAST, (void*)&optval, sizeof optval) < 0)
    syserr("setsockopt broadcast");  

  /* ustawienie TTL dla datagramów rozsyłanych do grupy */ 
  optval = TTL_VALUE;
  if (setsockopt(client[0].fd, IPPROTO_IP, IP_MULTICAST_TTL, (void*)&optval, sizeof optval) < 0)
    syserr("setsockopt multicast ttl");

  /* ustawienie adresu i portu odbiorcy */
  remote_address.sin_family = AF_INET;
  remote_address.sin_port = htons(remote_port);
  if (inet_aton(remote_dotted_address, &remote_address.sin_addr) == 0) 
  {
    fprintf(stderr, "ERROR: inet_aton - invalid multicast address\n");
    exit(EXIT_FAILURE);
  } 

  /* radosne rozgłaszanie czasu */
  for (int i = 0; i < REPEAT_COUNT; ++i) 
  {

    if (sendto(client[0].fd, "GET TIME", 8, 0, 
        (struct sockaddr *) &remote_address, sizeof(remote_address)) < 0) 
        syserr("send error");

    optval = 0;
    if (setsockopt(client[0].fd, SOL_SOCKET, SO_BROADCAST, (void*)&optval, sizeof optval) < 0)
      syserr("setsockopt broadcast error");

    printf("Sending request [%d]\n", i + 1);

    int ret = poll(client, 1, 3000);
    if (ret < 0)
      syserr("poll");    

    if (client[0].fd != -1 && (client[0].revents & (POLLIN | POLLERR))) 
    {	  
      struct sockaddr_in client_sock;
      socklen_t clientlen = sizeof(client_sock);
      int rval = recvfrom(client[0].fd, buffer, BUFSIZ, 0, (struct sockaddr *) &client_sock, &clientlen);

      if (rval < 0) 
      {
         fprintf(stderr, "Reading message (%d, %s)\n", errno, strerror(errno));
          if (close(client[0].fd) < 0)
            syserr("close error");
          client[0].fd = -1;
          break;
      }
      else if (rval == 0) 
      {
        fprintf(stderr, "Ending connection\n");
        if (close(client[0].fd) < 0)
          syserr("close error");
        client[0].fd = -1;
        break;
      }
      else // print feedback.
      {
        printf("Response from %s\n", inet_ntoa(client_sock.sin_addr));
        printf("Received time: %.*s", rval, buffer);
        i = REPEAT_COUNT;
      }
    }
    else if (i == REPEAT_COUNT - 1)
    {
      printf("Timeout: unable to receive response.\n");
    }
        
      
  }

  /* koniec */
  close(client[0].fd);
  exit(EXIT_SUCCESS);
}

// ./multi-send 239.10.11.12 10001
// ./multi-recv 239.10.11.12 10001
