// Overlay fragment — append writeFileAtomic implementation into environment.cc
// Applied by scripts/package/apply_qjs_writefile_atomic.sh

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <system_error>

std::filesystem::path Environment::resolveUnderUserData(const std::string& path) {
  if (path.empty()) {
    throw std::runtime_error("writeFileAtomic: empty path");
  }
  namespace fs = std::filesystem;
  fs::path userRoot = fs::path(getUserDataDir()).lexically_normal();
  fs::path requested = fs::path(path);
  if (requested.is_absolute()) {
    // Absolute paths must still stay under userDataDir.
  } else {
    requested = userRoot / requested;
  }
  requested = requested.lexically_normal();
  auto userStr = userRoot.string();
  auto reqStr = requested.string();
  if (reqStr != userStr && reqStr.rfind(userStr + "/", 0) != 0) {
    throw std::runtime_error("writeFileAtomic: path escapes userDataDir");
  }
  if (reqStr.find("..") != std::string::npos) {
    // Extra guard after lexical normalize.
    throw std::runtime_error("writeFileAtomic: path contains ..");
  }
  return requested;
}

void Environment::writeFileAtomic(const std::string& path, const std::string& content) {
  namespace fs = std::filesystem;
  const fs::path target = resolveUnderUserData(path);
  if (target.has_parent_path()) {
    fs::create_directories(target.parent_path());
  }
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
  // Best-effort fsync
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
}
