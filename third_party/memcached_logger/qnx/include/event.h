/* Header-only stand-in for libevent's <event.h>: logger.c never calls libevent, but memcached.h
   names its types. Sizes are placeholders, nothing here is ever executed. */
#pragma once
struct event_base;
struct event { char opaque[256]; };
struct evbuffer;
typedef int evutil_socket_t;
