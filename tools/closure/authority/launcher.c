#define _GNU_SOURCE

#include "profile.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef AT_EMPTY_PATH
#define AT_EMPTY_PATH 0x1000
#endif

#define DIAGNOSTIC_LIMIT (4U * 1024U * 1024U)
#define MANIFEST_HEADER "KILIX-F120-CLOSURE-MANIFEST-v1\n"
#define RESULT_LIMIT 4096U
#define RUN_TIMEOUT_SECONDS 900

struct sha256 {
    uint32_t state[8];
    uint64_t bits;
    unsigned char block[64];
    size_t used;
};

static uint32_t rotate_right(uint32_t value, unsigned count) {
    return (value >> count) | (value << (32U - count));
}

static void sha256_transform(struct sha256 *context, const unsigned char block[64]) {
    static const uint32_t constants[64] = {
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
        0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
        0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
        0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
        0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
        0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
        0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
        0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
        0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
        0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
        0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
    };
    uint32_t words[64];
    for (size_t index = 0; index < 16; ++index) {
        words[index] = ((uint32_t)block[index * 4] << 24) |
                       ((uint32_t)block[index * 4 + 1] << 16) |
                       ((uint32_t)block[index * 4 + 2] << 8) |
                       (uint32_t)block[index * 4 + 3];
    }
    for (size_t index = 16; index < 64; ++index) {
        uint32_t left = words[index - 15];
        uint32_t right = words[index - 2];
        uint32_t s0 = rotate_right(left, 7) ^ rotate_right(left, 18) ^ (left >> 3);
        uint32_t s1 = rotate_right(right, 17) ^ rotate_right(right, 19) ^ (right >> 10);
        words[index] = words[index - 16] + s0 + words[index - 7] + s1;
    }
    uint32_t a = context->state[0], b = context->state[1];
    uint32_t c = context->state[2], d = context->state[3];
    uint32_t e = context->state[4], f = context->state[5];
    uint32_t g = context->state[6], h = context->state[7];
    for (size_t index = 0; index < 64; ++index) {
        uint32_t sum1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
        uint32_t choose = (e & f) ^ ((~e) & g);
        uint32_t first = h + sum1 + choose + constants[index] + words[index];
        uint32_t sum0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t second = sum0 + majority;
        h = g; g = f; f = e; e = d + first;
        d = c; c = b; b = a; a = first + second;
    }
    context->state[0] += a; context->state[1] += b;
    context->state[2] += c; context->state[3] += d;
    context->state[4] += e; context->state[5] += f;
    context->state[6] += g; context->state[7] += h;
}

static void sha256_init(struct sha256 *context) {
    static const uint32_t initial[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };
    memcpy(context->state, initial, sizeof(initial));
    context->bits = 0;
    context->used = 0;
}

static void sha256_update(struct sha256 *context, const void *raw, size_t length) {
    const unsigned char *data = raw;
    context->bits += (uint64_t)length * 8U;
    while (length > 0) {
        size_t available = sizeof(context->block) - context->used;
        size_t amount = length < available ? length : available;
        memcpy(context->block + context->used, data, amount);
        context->used += amount;
        data += amount;
        length -= amount;
        if (context->used == sizeof(context->block)) {
            sha256_transform(context, context->block);
            context->used = 0;
        }
    }
}

static void sha256_final(struct sha256 *context, unsigned char output[32]) {
    uint64_t bits = context->bits;
    unsigned char marker = 0x80;
    unsigned char zero = 0;
    sha256_update(context, &marker, 1);
    while (context->used != 56) {
        sha256_update(context, &zero, 1);
    }
    unsigned char length[8];
    for (size_t index = 0; index < 8; ++index) {
        length[7 - index] = (unsigned char)(bits >> (index * 8));
    }
    sha256_update(context, length, sizeof(length));
    for (size_t index = 0; index < 8; ++index) {
        output[index * 4] = (unsigned char)(context->state[index] >> 24);
        output[index * 4 + 1] = (unsigned char)(context->state[index] >> 16);
        output[index * 4 + 2] = (unsigned char)(context->state[index] >> 8);
        output[index * 4 + 3] = (unsigned char)context->state[index];
    }
}

static void digest_hex(const unsigned char digest[32], char output[65]) {
    static const char alphabet[] = "0123456789abcdef";
    for (size_t index = 0; index < 32; ++index) {
        output[index * 2] = alphabet[digest[index] >> 4];
        output[index * 2 + 1] = alphabet[digest[index] & 15U];
    }
    output[64] = '\0';
}

static int sha256_fd(int descriptor, char output[65]) {
    struct sha256 context;
    sha256_init(&context);
    unsigned char buffer[1024 * 1024];
    off_t offset = 0;
    while (true) {
        ssize_t amount = pread(descriptor, buffer, sizeof(buffer), offset);
        if (amount < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (amount == 0) break;
        sha256_update(&context, buffer, (size_t)amount);
        offset += amount;
    }
    unsigned char digest[32];
    sha256_final(&context, digest);
    digest_hex(digest, output);
    return 0;
}

struct identity {
    dev_t device;
    ino_t inode;
};

struct manifest_walk {
    struct sha256 digest;
    dev_t device;
    bool reject_reserved;
    struct identity *identities;
    size_t identity_count;
    size_t identity_capacity;
};

static int remember_identity(struct manifest_walk *walk, dev_t device, ino_t inode) {
    for (size_t index = 0; index < walk->identity_count; ++index) {
        if (walk->identities[index].device == device && walk->identities[index].inode == inode) {
            errno = ELOOP;
            return -1;
        }
    }
    if (walk->identity_count == walk->identity_capacity) {
        size_t capacity = walk->identity_capacity ? walk->identity_capacity * 2 : 128;
        struct identity *items = realloc(walk->identities, capacity * sizeof(*items));
        if (!items) return -1;
        walk->identities = items;
        walk->identity_capacity = capacity;
    }
    walk->identities[walk->identity_count++] = (struct identity){device, inode};
    return 0;
}

static int compare_names(const void *left, const void *right) {
    const char *const *a = left;
    const char *const *b = right;
    return strcmp(*a, *b);
}

static bool reserved_name(const char *name) {
    size_t length = strlen(name);
    return strcmp(name, "sitecustomize.py") == 0 ||
           strcmp(name, "usercustomize.py") == 0 ||
           (length >= 4 && strcmp(name + length - 4, ".pth") == 0);
}

static int hash_manifest_directory(struct manifest_walk *walk, int directory,
                                   const char *prefix) {
    int duplicate = dup(directory);
    if (duplicate < 0) return -1;
    DIR *stream = fdopendir(duplicate);
    if (!stream) {
        close(duplicate);
        return -1;
    }
    char **names = NULL;
    size_t count = 0, capacity = 0;
    errno = 0;
    struct dirent *entry;
    while ((entry = readdir(stream)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) continue;
        if (strpbrk(entry->d_name, "\n\r\t/") != NULL) {
            errno = EINVAL;
            goto fail;
        }
        if (count == capacity) {
            size_t next = capacity ? capacity * 2 : 64;
            char **replacement = realloc(names, next * sizeof(*replacement));
            if (!replacement) goto fail;
            names = replacement;
            capacity = next;
        }
        names[count] = strdup(entry->d_name);
        if (!names[count]) goto fail;
        ++count;
    }
    if (errno != 0) goto fail;
    qsort(names, count, sizeof(*names), compare_names);
    for (size_t index = 0; index < count; ++index) {
        const char *name = names[index];
        if (walk->reject_reserved && reserved_name(name)) {
            errno = EPERM;
            goto fail;
        }
        struct stat information;
        if (fstatat(directory, name, &information, AT_SYMLINK_NOFOLLOW) < 0) goto fail;
        if (information.st_dev != walk->device ||
            remember_identity(walk, information.st_dev, information.st_ino) < 0) goto fail;
        size_t relative_length = strlen(prefix) + strlen(name);
        char *relative = malloc(relative_length + 1);
        if (!relative) goto fail;
        snprintf(relative, relative_length + 1, "%s%s", prefix, name);
        char line[8192];
        if (S_ISDIR(information.st_mode)) {
            int amount = snprintf(line, sizeof(line), "d\t%04o\t0\t-\t%s\n",
                                  information.st_mode & 07777, relative);
            if (amount < 0 || (size_t)amount >= sizeof(line)) {
                free(relative); errno = ENAMETOOLONG; goto fail;
            }
            sha256_update(&walk->digest, line, (size_t)amount);
            int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            if (child < 0) { free(relative); goto fail; }
            char *next_prefix = malloc(relative_length + 2);
            if (!next_prefix) { close(child); free(relative); goto fail; }
            snprintf(next_prefix, relative_length + 2, "%s/", relative);
            int outcome = hash_manifest_directory(walk, child, next_prefix);
            free(next_prefix);
            close(child);
            free(relative);
            if (outcome < 0) goto fail;
        } else if (S_ISREG(information.st_mode)) {
            int child = openat(directory, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
            if (child < 0) { free(relative); goto fail; }
            struct stat current;
            char file_digest[65];
            if (fstat(child, &current) < 0 || current.st_dev != information.st_dev ||
                current.st_ino != information.st_ino || sha256_fd(child, file_digest) < 0) {
                close(child); free(relative); goto fail;
            }
            close(child);
            int amount = snprintf(line, sizeof(line), "f\t%04o\t%jd\t%s\t%s\n",
                                  information.st_mode & 07777, (intmax_t)information.st_size,
                                  file_digest, relative);
            free(relative);
            if (amount < 0 || (size_t)amount >= sizeof(line)) {
                errno = ENAMETOOLONG; goto fail;
            }
            sha256_update(&walk->digest, line, (size_t)amount);
        } else {
            free(relative); errno = EINVAL; goto fail;
        }
    }
    for (size_t index = 0; index < count; ++index) free(names[index]);
    free(names);
    closedir(stream);
    return 0;

fail:
    {
        int saved = errno ? errno : EIO;
        for (size_t index = 0; index < count; ++index) free(names[index]);
        free(names);
        closedir(stream);
        errno = saved;
        return -1;
    }
}

static int observed_manifest_digest(int root, bool reject_reserved, char output[65]) {
    struct stat information;
    if (fstat(root, &information) < 0 || !S_ISDIR(information.st_mode)) return -1;
    struct manifest_walk walk = {0};
    sha256_init(&walk.digest);
    sha256_update(&walk.digest, MANIFEST_HEADER, strlen(MANIFEST_HEADER));
    walk.device = information.st_dev;
    walk.reject_reserved = reject_reserved;
    if (remember_identity(&walk, information.st_dev, information.st_ino) < 0 ||
        hash_manifest_directory(&walk, root, "") < 0) {
        free(walk.identities);
        return -1;
    }
    unsigned char digest[32];
    sha256_final(&walk.digest, digest);
    digest_hex(digest, output);
    free(walk.identities);
    return 0;
}

static int verify_manifest(int root, int manifest, const char *expected, bool reserved) {
    char manifest_digest[65], observed_digest[65];
    if (sha256_fd(manifest, manifest_digest) < 0 || strcmp(manifest_digest, expected) != 0) {
        errno = EBADMSG;
        return -1;
    }
    if (observed_manifest_digest(root, reserved, observed_digest) < 0 ||
        strcmp(observed_digest, expected) != 0) {
        errno = EBADMSG;
        return -1;
    }
    if (lseek(root, 0, SEEK_SET) < 0) return -1;
    return 0;
}

static int make_inheritable(int descriptor) {
    int flags = fcntl(descriptor, F_GETFD);
    return flags < 0 ? -1 : fcntl(descriptor, F_SETFD, flags & ~FD_CLOEXEC);
}

static bool path_contains(const char *root, const char *candidate) {
    size_t length = strlen(root);
    return strncmp(root, candidate, length) == 0 &&
           (candidate[length] == '\0' || candidate[length] == '/');
}

static int open_read_only_at(int parent, const char *name, bool directory) {
    int flags = O_RDONLY | O_NOFOLLOW | O_CLOEXEC;
    if (directory) flags |= O_DIRECTORY;
    int descriptor = openat(parent, name, flags);
    if (descriptor < 0) return -1;
    struct stat information;
    if (fstat(descriptor, &information) < 0 ||
        (directory ? !S_ISDIR(information.st_mode) : !S_ISREG(information.st_mode)) ||
        (information.st_mode & 0222) != 0) {
        close(descriptor);
        errno = EPERM;
        return -1;
    }
    return descriptor;
}

static int random_run_id(char output[33]) {
    int descriptor = open("/dev/urandom", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) return -1;
    unsigned char bytes[16];
    size_t offset = 0;
    while (offset < sizeof(bytes)) {
        ssize_t amount = read(descriptor, bytes + offset, sizeof(bytes) - offset);
        if (amount < 0 && errno == EINTR) continue;
        if (amount <= 0) { close(descriptor); return -1; }
        offset += (size_t)amount;
    }
    close(descriptor);
    static const char alphabet[] = "0123456789abcdef";
    for (size_t index = 0; index < sizeof(bytes); ++index) {
        output[index * 2] = alphabet[bytes[index] >> 4];
        output[index * 2 + 1] = alphabet[bytes[index] & 15U];
    }
    output[32] = '\0';
    return 0;
}

static int set_nonblocking(int descriptor) {
    int flags = fcntl(descriptor, F_GETFL);
    return flags < 0 ? -1 : fcntl(descriptor, F_SETFL, flags | O_NONBLOCK);
}

static int forward_bytes(int input, int output, size_t *total, unsigned char *result,
                         size_t *result_size, bool is_result, bool *eof) {
    unsigned char buffer[8192];
    while (true) {
        ssize_t amount = read(input, buffer, sizeof(buffer));
        if (amount > 0) {
            if (is_result) {
                if (*result_size + (size_t)amount > RESULT_LIMIT) return -2;
                memcpy(result + *result_size, buffer, (size_t)amount);
                *result_size += (size_t)amount;
            } else {
                if (*total + (size_t)amount > DIAGNOSTIC_LIMIT) return -2;
                *total += (size_t)amount;
                size_t offset = 0;
                while (offset < (size_t)amount) {
                    ssize_t written = write(output, buffer + offset, (size_t)amount - offset);
                    if (written < 0 && errno == EINTR) continue;
                    if (written < 0) return -1;
                    offset += (size_t)written;
                }
            }
            continue;
        }
        if (amount == 0) { *eof = true; return 0; }
        if (errno == EINTR) continue;
        if (errno == EAGAIN || errno == EWOULDBLOCK) return 0;
        return -1;
    }
}

static int supervise(pid_t child, int stdout_fd, int stderr_fd, int result_fd,
                     unsigned char result[RESULT_LIMIT], size_t *result_size,
                     int *child_status) {
    if (set_nonblocking(stdout_fd) < 0 || set_nonblocking(stderr_fd) < 0 ||
        set_nonblocking(result_fd) < 0) return -1;
    bool out_eof = false, err_eof = false, result_eof = false, reaped = false;
    size_t out_total = 0, err_total = 0;
    time_t started = time(NULL);
    while (!(out_eof && err_eof && result_eof && reaped)) {
        if (time(NULL) - started > RUN_TIMEOUT_SECONDS) {
            kill(-child, SIGKILL);
            errno = ETIMEDOUT;
            return -2;
        }
        struct pollfd descriptors[3] = {
            {stdout_fd, POLLIN | POLLHUP, 0},
            {stderr_fd, POLLIN | POLLHUP, 0},
            {result_fd, POLLIN | POLLHUP, 0},
        };
        if (poll(descriptors, 3, 100) < 0 && errno != EINTR) return -1;
        int outcome;
        if (!out_eof && (outcome = forward_bytes(stdout_fd, STDOUT_FILENO, &out_total,
                                                  result, result_size, false, &out_eof)) != 0)
            return outcome;
        if (!err_eof && (outcome = forward_bytes(stderr_fd, STDERR_FILENO, &err_total,
                                                  result, result_size, false, &err_eof)) != 0)
            return outcome;
        size_t ignored = 0;
        if (!result_eof && (outcome = forward_bytes(result_fd, -1, &ignored,
                                                     result, result_size, true, &result_eof)) != 0)
            return outcome;
        if (!reaped) {
            pid_t waited = waitpid(child, child_status, WNOHANG);
            if (waited < 0) return -1;
            reaped = waited == child;
        }
    }
    return 0;
}

static void refusal(const char *reason) {
    dprintf(STDERR_FILENO, "F120_AUTHORITY_REFUSAL: %s\n", reason);
}

int main(int argc, char **argv) {
    if (argc < 4 || strcmp(argv[1], "--subject") != 0 || argv[2][0] != '/' ||
        (strcmp(argv[3], "check") != 0 && strcmp(argv[3], "cli") != 0) ||
        (strcmp(argv[3], "check") == 0 && argc != 4) ||
        (strcmp(argv[3], "cli") == 0 && argc == 4)) {
        refusal("usage is f120-authority --subject ABSOLUTE check|cli [ARGS...]");
        return 2;
    }
    const char *command = argv[3];
    struct stat subject_lstat;
    if (lstat(argv[2], &subject_lstat) < 0 || !S_ISDIR(subject_lstat.st_mode)) {
        refusal("subject is absent, symlinked or not a directory");
        return 2;
    }
    char subject_path[PATH_MAX];
    if (!realpath(argv[2], subject_path)) {
        refusal("cannot resolve subject path");
        return 2;
    }
    int subject_fd = open(subject_path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat subject_information;
    if (subject_fd < 0 || fstat(subject_fd, &subject_information) < 0 ||
        subject_information.st_dev != subject_lstat.st_dev ||
        subject_information.st_ino != subject_lstat.st_ino) {
        refusal("cannot retain stable subject descriptor");
        if (subject_fd >= 0) close(subject_fd);
        return 2;
    }

    char executable[PATH_MAX], bundle_path[PATH_MAX];
    ssize_t executable_length = readlink("/proc/self/exe", executable, sizeof(executable) - 1);
    if (executable_length <= 0 || (size_t)executable_length >= sizeof(executable) - 1) {
        refusal("cannot resolve launcher identity");
        close(subject_fd);
        return 2;
    }
    executable[executable_length] = '\0';
    char *slash = strrchr(executable, '/');
    if (!slash) { refusal("launcher path is malformed"); close(subject_fd); return 2; }
    *slash = '\0';
    if (!realpath(executable, bundle_path) || path_contains(subject_path, bundle_path) ||
        path_contains(bundle_path, subject_path)) {
        refusal("authority bundle overlaps the subject");
        close(subject_fd);
        return 2;
    }
    int bundle_fd = open(bundle_path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    int bootstrap_fd = -1, subject_manifest_fd = -1, runtime_fd = -1;
    int runtime_manifest_fd = -1, dependency_fd = -1, dependency_manifest_fd = -1;
    int python_fd = -1;
    if (bundle_fd < 0 ||
        (bootstrap_fd = open_read_only_at(bundle_fd, "bootstrap.py", false)) < 0 ||
        (subject_manifest_fd = open_read_only_at(bundle_fd, "subject.manifest", false)) < 0 ||
        (runtime_fd = open_read_only_at(bundle_fd, "runtime", true)) < 0 ||
        (runtime_manifest_fd = open_read_only_at(bundle_fd, "runtime.manifest", false)) < 0 ||
        (dependency_fd = open_read_only_at(bundle_fd, "dependencies", true)) < 0 ||
        (dependency_manifest_fd = open_read_only_at(bundle_fd, "dependency.manifest", false)) < 0) {
        refusal("authority bundle bytes are absent, writable or non-regular");
        goto fail;
    }
    int runtime_bin = openat(runtime_fd, "bin", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (runtime_bin < 0 ||
        (python_fd = openat(runtime_bin, F120_PYTHON_BASENAME,
                            O_RDONLY | O_NOFOLLOW | O_CLOEXEC)) < 0) {
        refusal("pinned interpreter is absent from runtime");
        if (runtime_bin >= 0) close(runtime_bin);
        goto fail;
    }
    close(runtime_bin);
    struct stat python_information;
    char actual[65];
    if (fstat(python_fd, &python_information) < 0 || !S_ISREG(python_information.st_mode) ||
        (python_information.st_mode & 0222) != 0 || sha256_fd(python_fd, actual) < 0 ||
        strcmp(actual, F120_PYTHON_SHA256) != 0 || sha256_fd(bootstrap_fd, actual) < 0 ||
        strcmp(actual, F120_BOOTSTRAP_SHA256) != 0) {
        refusal("interpreter or bootstrap identity mismatch");
        goto fail;
    }
    if (verify_manifest(runtime_fd, runtime_manifest_fd,
                        F120_RUNTIME_MANIFEST_SHA256, false) < 0) {
        refusal("runtime closure differs from its pinned manifest");
        goto fail;
    }
    if (verify_manifest(dependency_fd, dependency_manifest_fd,
                        F120_DEPENDENCY_MANIFEST_SHA256, false) < 0) {
        refusal("dependency closure differs from its pinned manifest");
        goto fail;
    }
    if (verify_manifest(subject_fd, subject_manifest_fd,
                        F120_SUBJECT_MANIFEST_SHA256, true) < 0) {
        refusal("subject closure differs from its pinned manifest");
        goto fail;
    }

    char temporary[] = "/tmp/kilix-f120-authority.XXXXXX";
    if (!mkdtemp(temporary) || chmod(temporary, 0700) < 0 ||
        path_contains(subject_path, temporary) || path_contains(bundle_path, temporary)) {
        refusal("cannot create disjoint empty authority cwd");
        goto fail;
    }
    int result_pipe[2] = {-1, -1}, out_pipe[2] = {-1, -1}, err_pipe[2] = {-1, -1};
    if (pipe2(result_pipe, O_CLOEXEC) < 0 || pipe2(out_pipe, O_CLOEXEC) < 0 ||
        pipe2(err_pipe, O_CLOEXEC) < 0) {
        refusal("cannot create bounded result channels");
        rmdir(temporary);
        goto fail;
    }
    int inherited[] = {subject_fd, bootstrap_fd, subject_manifest_fd, runtime_fd,
                       runtime_manifest_fd, dependency_fd, dependency_manifest_fd,
                       python_fd, result_pipe[1]};
    for (size_t index = 0; index < sizeof(inherited) / sizeof(inherited[0]); ++index) {
        if (make_inheritable(inherited[index]) < 0) {
            refusal("cannot retain authority descriptors across exec");
            rmdir(temporary);
            goto fail_pipes;
        }
    }
    char run_id[33];
    if (random_run_id(run_id) < 0) {
        refusal("cannot create run identity");
        rmdir(temporary);
        goto fail_pipes;
    }

    char bootstrap_path[64];
    snprintf(bootstrap_path, sizeof(bootstrap_path), "/proc/self/fd/%d", bootstrap_fd);
    size_t python_path_size = strlen(bundle_path) + strlen(F120_PYTHON_BASENAME) + 15;
    char *python_path = malloc(python_path_size);
    if (!python_path) {
        refusal("cannot allocate pinned interpreter path");
        rmdir(temporary);
        goto fail_pipes;
    }
    snprintf(python_path, python_path_size, "%s/runtime/bin/%s", bundle_path,
             F120_PYTHON_BASENAME);
    char bootstrap_number[32], python_number[32], runtime_number[32];
    char runtime_manifest_number[32], dependency_number[32], dependency_manifest_number[32];
    char subject_number[32], subject_manifest_number[32], result_number[32];
    char device_number[64], inode_number[64];
    snprintf(bootstrap_number, sizeof(bootstrap_number), "%d", bootstrap_fd);
    snprintf(python_number, sizeof(python_number), "%d", python_fd);
    snprintf(runtime_number, sizeof(runtime_number), "%d", runtime_fd);
    snprintf(runtime_manifest_number, sizeof(runtime_manifest_number), "%d", runtime_manifest_fd);
    snprintf(dependency_number, sizeof(dependency_number), "%d", dependency_fd);
    snprintf(dependency_manifest_number, sizeof(dependency_manifest_number), "%d", dependency_manifest_fd);
    snprintf(subject_number, sizeof(subject_number), "%d", subject_fd);
    snprintf(subject_manifest_number, sizeof(subject_manifest_number), "%d", subject_manifest_fd);
    snprintf(result_number, sizeof(result_number), "%d", result_pipe[1]);
    snprintf(device_number, sizeof(device_number), "%ju", (uintmax_t)subject_information.st_dev);
    snprintf(inode_number, sizeof(inode_number), "%ju", (uintmax_t)subject_information.st_ino);

    size_t fixed_count = 48;
    size_t forwarded = strcmp(command, "cli") == 0 ? (size_t)(argc - 4) : 0;
    char **python_argv = calloc(fixed_count + forwarded + 1, sizeof(*python_argv));
    if (!python_argv) {
        refusal("cannot allocate fixed launch argv");
        free(python_path);
        rmdir(temporary);
        goto fail_pipes;
    }
    size_t position = 0;
#define ARG(value) python_argv[position++] = (char *)(value)
    ARG(python_path); ARG("-I"); ARG("-S"); ARG("-B"); ARG(bootstrap_path);
    ARG("--mode"); ARG("outer");
    ARG("--bootstrap-fd"); ARG(bootstrap_number);
    ARG("--bootstrap-sha256"); ARG(F120_BOOTSTRAP_SHA256);
    ARG("--python-fd"); ARG(python_number);
    ARG("--python-sha256"); ARG(F120_PYTHON_SHA256);
    ARG("--runtime-fd"); ARG(runtime_number);
    ARG("--runtime-manifest-fd"); ARG(runtime_manifest_number);
    ARG("--runtime-manifest-sha256"); ARG(F120_RUNTIME_MANIFEST_SHA256);
    ARG("--dependency-fd"); ARG(dependency_number);
    ARG("--dependency-manifest-fd"); ARG(dependency_manifest_number);
    ARG("--dependency-manifest-sha256"); ARG(F120_DEPENDENCY_MANIFEST_SHA256);
    ARG("--subject-fd"); ARG(subject_number);
    ARG("--subject-path"); ARG(subject_path);
    ARG("--subject-device"); ARG(device_number);
    ARG("--subject-inode"); ARG(inode_number);
    ARG("--subject-manifest-fd"); ARG(subject_manifest_number);
    ARG("--subject-manifest-sha256"); ARG(F120_SUBJECT_MANIFEST_SHA256);
    ARG("--result-fd"); ARG(result_number);
    ARG("--run-id"); ARG(run_id);
    ARG("--tmpdir"); ARG(temporary);
    ARG("--command"); ARG(command);
    ARG("--");
    for (int index = 4; index < argc; ++index) ARG(argv[index]);
#undef ARG
    python_argv[position] = NULL;
    if (position != fixed_count + forwarded) {
        refusal("internal launch argv construction mismatch");
        free(python_argv);
        free(python_path);
        rmdir(temporary);
        goto fail_pipes;
    }
    char tmp_environment[PATH_MAX + 16];
    snprintf(tmp_environment, sizeof(tmp_environment), "TMPDIR=%s", temporary);
    char *environment[] = {
        "LC_ALL=C.UTF-8", "PATH=/usr/bin:/bin", tmp_environment, "TZ=UTC", NULL,
    };

    pid_t child = fork();
    if (child < 0) {
        refusal("cannot fork authority process");
        free(python_argv);
        free(python_path);
        rmdir(temporary);
        goto fail_pipes;
    }
    if (child == 0) {
        setpgid(0, 0);
        close(result_pipe[0]); close(out_pipe[0]); close(err_pipe[0]);
        if (chdir(temporary) < 0 || dup2(out_pipe[1], STDOUT_FILENO) < 0 ||
            dup2(err_pipe[1], STDERR_FILENO) < 0) _exit(126);
        close(out_pipe[1]); close(err_pipe[1]);
        syscall(SYS_execveat, python_fd, "", python_argv, environment, AT_EMPTY_PATH);
        _exit(126);
    }
    setpgid(child, child);
    close(result_pipe[1]); close(out_pipe[1]); close(err_pipe[1]);
    unsigned char result[RESULT_LIMIT];
    size_t result_size = 0;
    int child_status = 0;
    int supervised = supervise(child, out_pipe[0], err_pipe[0], result_pipe[0],
                               result, &result_size, &child_status);
    close(result_pipe[0]); close(out_pipe[0]); close(err_pipe[0]);
    if (supervised != 0) {
        kill(-child, SIGKILL);
        waitpid(child, NULL, 0);
    }
    free(python_argv);
    free(python_path);

    char expected[1024];
    int expected_size = snprintf(
        expected, sizeof(expected),
        "{\"command\":\"%s\",\"manifest_sha256\":\"%s\",\"run_id\":\"%s\","
        "\"schema\":\"kilix.f120.authority-result/v1\",\"status\":\"accepted\","
        "\"subject_device\":%ju,\"subject_inode\":%ju}\n",
        command, F120_SUBJECT_MANIFEST_SHA256, run_id,
        (uintmax_t)subject_information.st_dev, (uintmax_t)subject_information.st_ino);
    bool accepted = supervised == 0 && WIFEXITED(child_status) &&
                    WEXITSTATUS(child_status) == 0 && expected_size > 0 &&
                    (size_t)expected_size == result_size &&
                    memcmp(expected, result, result_size) == 0;
    if (rmdir(temporary) < 0) accepted = false;
    if (!accepted) {
        refusal(supervised == -2 ? "bounded process supervision refused output or timeout" :
                                  "canonical terminal result absent or invalid");
        goto fail;
    }
    dprintf(STDOUT_FILENO, "F120_AUTHORITY_ACCEPTED %s", expected);
    close(python_fd); close(dependency_manifest_fd); close(dependency_fd);
    close(runtime_manifest_fd); close(runtime_fd); close(subject_manifest_fd);
    close(bootstrap_fd); close(bundle_fd); close(subject_fd);
    return 0;

fail_pipes:
    if (result_pipe[0] >= 0) close(result_pipe[0]);
    if (result_pipe[1] >= 0) close(result_pipe[1]);
    if (out_pipe[0] >= 0) close(out_pipe[0]);
    if (out_pipe[1] >= 0) close(out_pipe[1]);
    if (err_pipe[0] >= 0) close(err_pipe[0]);
    if (err_pipe[1] >= 0) close(err_pipe[1]);
fail:
    if (python_fd >= 0) close(python_fd);
    if (dependency_manifest_fd >= 0) close(dependency_manifest_fd);
    if (dependency_fd >= 0) close(dependency_fd);
    if (runtime_manifest_fd >= 0) close(runtime_manifest_fd);
    if (runtime_fd >= 0) close(runtime_fd);
    if (subject_manifest_fd >= 0) close(subject_manifest_fd);
    if (bootstrap_fd >= 0) close(bootstrap_fd);
    if (bundle_fd >= 0) close(bundle_fd);
    close(subject_fd);
    return 2;
}
