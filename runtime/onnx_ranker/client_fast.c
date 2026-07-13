/* Fast Unix-socket client for gu_ranker — no Python startup cost. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <errno.h>

static int connect_sock(const char *path, int timeout_ms) {
  int fd = socket(AF_UNIX, SOCK_STREAM, 0);
  if (fd < 0) return -1;
  struct timeval tv;
  tv.tv_sec = timeout_ms / 1000;
  tv.tv_usec = (timeout_ms % 1000) * 1000;
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
  struct sockaddr_un addr;
  memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);
  if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
    close(fd);
    return -1;
  }
  return fd;
}

int main(int argc, char **argv) {
  const char *sock = NULL;
  const char *json = NULL;
  int timeout_ms = 50;
  int use_stdin = 0;

  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--sock") && i + 1 < argc) sock = argv[++i];
    else if (!strcmp(argv[i], "--json") && i + 1 < argc) json = argv[++i];
    else if (!strcmp(argv[i], "--stdin") ) use_stdin = 1;
    else if (!strcmp(argv[i], "--timeout-ms") && i + 1 < argc) timeout_ms = atoi(argv[++i]);
  }
  if (!sock) sock = getenv("GU_RANKER_SOCK");
  if (!sock) {
    const char *home = getenv("HOME");
    static char buf[512];
    snprintf(buf, sizeof(buf), "%s/Library/Rime/run/gu_ranker.sock", home ? home : "");
    sock = buf;
  }

  char *payload = NULL;
  if (use_stdin) {
    size_t cap = 0, n = 0;
    char chunk[4096];
    payload = NULL;
    while (fgets(chunk, sizeof(chunk), stdin)) {
      size_t cl = strlen(chunk);
      payload = realloc(payload, n + cl + 1);
      memcpy(payload + n, chunk, cl);
      n += cl;
      payload[n] = 0;
    }
  } else if (json) {
    payload = strdup(json);
  }
  if (!payload || !payload[0]) {
    puts("{\"scores\":[]}");
    return 0;
  }

  int fd = connect_sock(sock, timeout_ms);
  if (fd < 0) {
    puts("{\"scores\":[],\"error\":\"connect\"}");
    free(payload);
    return 0;
  }
  size_t len = strlen(payload);
  /* ensure newline */
  if (payload[len - 1] != '\n') {
    payload = realloc(payload, len + 2);
    payload[len] = '\n';
    payload[len + 1] = 0;
    len += 1;
  }
  if (write(fd, payload, len) < 0) {
    puts("{\"scores\":[],\"error\":\"write\"}");
    close(fd);
    free(payload);
    return 0;
  }
  char out[65536];
  size_t got = 0;
  while (got + 1 < sizeof(out)) {
    ssize_t r = read(fd, out + got, sizeof(out) - 1 - got);
    if (r <= 0) break;
    got += (size_t)r;
    if (memchr(out, '\n', got)) break;
  }
  out[got] = 0;
  close(fd);
  free(payload);
  if (got == 0) {
    puts("{\"scores\":[],\"error\":\"empty\"}");
    return 0;
  }
  fputs(out, stdout);
  if (out[got - 1] != '\n') fputc('\n', stdout);
  return 0;
}
