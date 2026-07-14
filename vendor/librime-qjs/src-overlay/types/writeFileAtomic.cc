// Overlay fragment — portable writeFileAtomic for librime-qjs Environment.
// Applied by scripts/package/apply_qjs_writefile_atomic.sh
//
// POSIX: temp write → flush → fsync → mode 0600 → rename → parent dir sync
// Windows: temp write → FlushFileBuffers → ReplaceFileW / MoveFileExW

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <system_error>
#include <string>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace {

bool isUnderUserRoot(const std::filesystem::path& userRoot,
                     const std::filesystem::path& requested) {
  namespace fs = std::filesystem;
  std::error_code ec;
  const fs::path userCanon = fs::weakly_canonical(userRoot, ec);
  const fs::path reqCanon = fs::weakly_canonical(requested, ec);
  // Component-wise containment (not string-prefix).
  auto uit = userCanon.begin();
  auto rit = reqCanon.begin();
  for (; uit != userCanon.end() && rit != reqCanon.end(); ++uit, ++rit) {
    if (*uit != *rit) return false;
  }
  return uit == userCanon.end();
}

}  // namespace

std::filesystem::path Environment::resolveUnderUserData(const std::string& path) {
  if (path.empty()) {
    throw std::runtime_error("writeFileAtomic: empty path");
  }
  namespace fs = std::filesystem;
  fs::path userRoot = fs::path(getUserDataDir()).lexically_normal();
  fs::path requested = fs::path(path);
  if (!requested.is_absolute()) {
    requested = userRoot / requested;
  }
  requested = requested.lexically_normal();
  for (const auto& part : requested) {
    if (part == "..") {
      throw std::runtime_error("writeFileAtomic: path contains ..");
    }
  }
  if (!isUnderUserRoot(userRoot, requested)) {
    throw std::runtime_error("writeFileAtomic: path escapes userDataDir");
  }
  return requested;
}

void Environment::writeFileAtomic(const std::string& path, const std::string& content) {
  namespace fs = std::filesystem;
  const fs::path target = resolveUnderUserData(path);
  if (target.has_parent_path()) {
    fs::create_directories(target.parent_path());
  }

#if defined(_WIN32)
  const std::wstring tmpW =
      target.wstring() + L".tmp." + std::to_wstring(GetCurrentProcessId());
  {
    HANDLE h = CreateFileW(tmpW.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) {
      throw std::runtime_error("writeFileAtomic: cannot open tmp");
    }
    DWORD written = 0;
    if (!WriteFile(h, content.data(), static_cast<DWORD>(content.size()), &written, nullptr) ||
        written != content.size()) {
      CloseHandle(h);
      DeleteFileW(tmpW.c_str());
      throw std::runtime_error("writeFileAtomic: write failed");
    }
    FlushFileBuffers(h);
    CloseHandle(h);
  }
  BOOL ok = FALSE;
  if (GetFileAttributesW(target.wstring().c_str()) != INVALID_FILE_ATTRIBUTES) {
    ok = ReplaceFileW(target.wstring().c_str(), tmpW.c_str(), nullptr,
                      REPLACEFILE_IGNORE_MERGE_ERRORS, nullptr, nullptr);
  } else {
    ok = MoveFileExW(tmpW.c_str(), target.wstring().c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
  }
  if (!ok) {
    DeleteFileW(tmpW.c_str());
    throw std::runtime_error("writeFileAtomic: replace/move failed");
  }
#else
  const std::string tmp =
      target.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
  {
    std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
    if (!out) {
      throw std::runtime_error("writeFileAtomic: cannot open tmp");
    }
    out.write(content.data(), static_cast<std::streamsize>(content.size()));
    out.flush();
    if (!out) {
      fs::remove(tmp);
      throw std::runtime_error("writeFileAtomic: write failed");
    }
  }
  int fd = ::open(tmp.c_str(), O_RDONLY);
  if (fd >= 0) {
    ::fsync(fd);
    ::close(fd);
  }
  ::chmod(tmp.c_str(), S_IRUSR | S_IWUSR);
  std::error_code ec;
  fs::rename(tmp, target, ec);
  if (ec) {
    fs::remove(tmp);
    throw std::runtime_error("writeFileAtomic: rename failed: " + ec.message());
  }
  // Parent directory sync (best-effort durability).
  if (target.has_parent_path()) {
    int dirfd = ::open(target.parent_path().c_str(), O_RDONLY | O_DIRECTORY);
    if (dirfd >= 0) {
      ::fsync(dirfd);
      ::close(dirfd);
    }
  }
#endif
}
