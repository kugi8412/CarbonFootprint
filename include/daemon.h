#pragma once
#include "platform.h"

// ============================================================
// Daemon - Background process management
// ============================================================

class Daemon {
public:
    // Daemonize the current process (Linux/Mac: fork, Windows: no-op)
    static bool Daemonize();
    static void InstallSignalHandlers(std::function<void()> onStop);
    static bool IsDaemon();

private:
    static std::function<void()> stopCallback_;
    static bool isDaemon_;
    static std::atomic<bool> stopFired_;

#ifdef PLATFORM_WINDOWS
    static BOOL WINAPI ConsoleHandler(DWORD signal);
#else
    static void SignalHandler(int sig);
#endif
};
