#include "daemon.h"

// ============================================================
// Daemon Implementation - Cross-platform
// ============================================================

std::function<void()> Daemon::stopCallback_;
bool Daemon::isDaemon_ = false;
std::atomic<bool> Daemon::stopFired_{false};

#ifdef PLATFORM_WINDOWS

BOOL WINAPI Daemon::ConsoleHandler(DWORD signal) {
    if (signal == CTRL_C_EVENT || signal == CTRL_BREAK_EVENT || signal == CTRL_CLOSE_EVENT) {
        // Prevent re-entry: only fire once
        bool expected = false;
        if (stopFired_.compare_exchange_strong(expected, true)) {
            if (stopCallback_) {
                stopCallback_();
            }
        }
        return TRUE;
    }
    return FALSE;
}

bool Daemon::Daemonize() {
    isDaemon_ = true;
    return true;
}

void Daemon::InstallSignalHandlers(std::function<void()> onStop) {
    stopCallback_ = onStop;
    stopFired_ = false;
    SetConsoleCtrlHandler(ConsoleHandler, TRUE);
}

#else // Linux / Mac

void Daemon::SignalHandler(int sig) {
    if (sig == SIGINT || sig == SIGTERM || sig == SIGHUP) {
        // Prevent re-entry: only fire once
        bool expected = false;
        if (stopFired_.compare_exchange_strong(expected, true)) {
            // Reset signal handlers to default to prevent repeated firing
            signal(SIGINT, SIG_DFL);
            signal(SIGTERM, SIG_DFL);
            signal(SIGHUP, SIG_DFL);
            if (stopCallback_) {
                stopCallback_();
            }
        }
    }
}

bool Daemon::Daemonize() {
    pid_t pid = fork();
    if (pid < 0) {
        std::cerr << "Failed to fork daemon process.\n";
        return false;
    }
    if (pid > 0) {
        // Parent exits
        std::cout << "Daemon started with PID: " << pid << "\n";
        _exit(0);
    }

    // Child continues as daemon
    setsid();
    isDaemon_ = true;

    // Redirect stdin/stdout/stderr to /dev/null
    // Keep stdout/stderr for logging
    close(STDIN_FILENO);
    open("/dev/null", O_RDONLY); // stdin -> /dev/null

    return true;
}

void Daemon::InstallSignalHandlers(std::function<void()> onStop) {
    stopCallback_ = onStop;

    struct sigaction sa;
    sa.sa_handler = SignalHandler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;

    sigaction(SIGINT, &sa, nullptr);
    sigaction(SIGTERM, &sa, nullptr);
    sigaction(SIGHUP, &sa, nullptr);
}

#endif

bool Daemon::IsDaemon() {
    return isDaemon_;
}
