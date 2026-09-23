package cli

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/spf13/cobra"
)

var watchCmd = &cobra.Command{
	Use:   "watch [folder]",
	Short: "Watch a folder for new audio files",
	Args:  cobra.ExactArgs(1),
	Run:   runWatch,
}

func init() {
	rootCmd.AddCommand(watchCmd)
}

func runWatch(cmd *cobra.Command, args []string) {
	folder := args[0]
	absPath, err := filepath.Abs(folder)
	if err != nil {
		log.Fatalf("Failed to get absolute path: %v", err)
	}

	if _, err := os.Stat(absPath); os.IsNotExist(err) {
		log.Fatalf("Folder does not exist: %s", absPath)
	}

	// Save as current watch folder
	if _, err := SaveConfig("", "", absPath); err != nil {
		fmt.Printf("Warning: Failed to save watch folder to config: %v\n", err)
	}

	watchFolder(absPath)
}

func watchFolder(path string) {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if err := watchFolderContext(ctx, path); err != nil {
		log.Printf("Watcher stopped: %v", err)
	}
}

func watchFolderContext(ctx context.Context, path string) error {
	return watchFolderWithUpload(ctx, path, func(ctx context.Context, filename string) error {
		return uploadFileContext(ctx, GetConfig(), filename, &http.Client{Timeout: uploadTimeout})
	})
}

func watchFolderWithUpload(ctx context.Context, path string, upload func(context.Context, string) error) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	defer watcher.Close()
	if err := watcher.Add(path); err != nil {
		return err
	}
	// A burst cannot create unbounded upload goroutines or read files into memory.
	pending := make(chan string, 16)
	var workers sync.WaitGroup
	for index := 0; index < 2; index++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case filename, ok := <-pending:
					if !ok {
						return
					}
					jobCtx, cancel := context.WithTimeout(ctx, uploadTimeout)
					err := upload(jobCtx, filename)
					cancel()
					if err != nil {
						log.Printf("Upload failed; original retained at %s: %v", filename, err)
					}
				}
			}
		}()
	}
	// Debounce within this single event loop: no per-file timer goroutines.
	due := make(map[string]time.Time)
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	defer func() { cancel(); close(pending); workers.Wait() }()
	log.Printf("Watching %s for new audio files", path)
	for {
		select {
		case <-ctx.Done():
			return nil
		case event, ok := <-watcher.Events:
			if !ok {
				return nil
			}
			if event.Op&(fsnotify.Write|fsnotify.Create) != 0 && isAudioFile(strings.ToLower(filepath.Ext(event.Name))) {
				if _, exists := due[event.Name]; exists || len(due) < 128 {
					due[event.Name] = time.Now().Add(2 * time.Second)
				} else {
					log.Printf("Upload backlog full; original retained for retry: %s", event.Name)
				}
			}
		case err, ok := <-watcher.Errors:
			if !ok {
				return nil
			}
			log.Printf("Watcher error: %v", err)
		case now := <-ticker.C:
			for filename, deadline := range due {
				if deadline.After(now) {
					continue
				}
				select {
				case pending <- filename:
					delete(due, filename)
				default:
				}
			}
		}
	}
}

func isAudioFile(ext string) bool {
	switch ext {
	case ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma":
		return true
	default:
		return false
	}
}
