package main

import (
	"log/slog"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	slog.Info("bot runtime placeholder — wire pipeline in slice 1 step 8", "service", "bot")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	slog.Info("bot shutting down")
}
