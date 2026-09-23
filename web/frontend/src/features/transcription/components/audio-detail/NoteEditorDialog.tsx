import { useState, useEffect, useRef } from "react";
import { useIsMobile } from "@/hooks/use-mobile";
import { X, StickyNote } from "lucide-react";
import { Button } from "@/components/ui/button";

interface NoteEditorDialogProps {
    isOpen: boolean;
    quote: string;
    position: { x: number; y: number };
    onSave: (content: string) => Promise<void>;
    onSaved: () => void;
    onCancel: () => void;
}

export function NoteEditorDialog({
    isOpen,
    quote,
    position,
    onSave,
    onSaved,
    onCancel
}: NoteEditorDialogProps) {
    const isMobile = useIsMobile();
    const [content, setContent] = useState("");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const editorVersion = useRef(0);
    const savingRef = useRef(false);

    // Focus textarea on mount and reset content
    useEffect(() => {
        editorVersion.current += 1;
        savingRef.current = false;
        setSaving(false);
        let focusTimer: ReturnType<typeof setTimeout> | undefined;
        if (isOpen) {
            setContent("");
            setError("");
            // Delay focus to ensure element is mounted
            focusTimer = setTimeout(() => textareaRef.current?.focus(), 50);
        }
        return () => {
            editorVersion.current += 1;
            clearTimeout(focusTimer);
        };
    }, [isOpen, quote]);

    if (!isOpen) return null;

    // Mobile: Center on screen with backdrop
    // Desktop: Position near selection
    const containerStyle: React.CSSProperties = isMobile ? {
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
        zIndex: 10001,
        backgroundColor: 'rgba(0, 0, 0, 0.4)',
        backdropFilter: 'blur(4px)'
    } : {
        position: 'fixed',
        left: Math.min(Math.max(position.x, 200), window.innerWidth - 200),
        top: position.y + 24,
        transform: 'translateX(-50%)',
        zIndex: 10001
    };

    const handleSubmit = async () => {
        if (!content.trim() || savingRef.current) return;
        const version = editorVersion.current;
        savingRef.current = true;
        setSaving(true); setError("");
        try {
            await onSave(content);
            if (editorVersion.current === version) onSaved();
        } catch (cause) {
            if (editorVersion.current === version) {
                setError(cause instanceof Error ? cause.message : "Note was not saved. Please retry.");
            }
        } finally {
            if (editorVersion.current === version) {
                savingRef.current = false;
                setSaving(false);
            }
        }
    };

    const handleCancel = () => {
        if (!savingRef.current) onCancel();
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        // Submit on Cmd/Ctrl + Enter
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            handleSubmit();
        }
        // Close on Escape
        if (e.key === 'Escape') {
            e.preventDefault();
            handleCancel();
        }
    };

    return (
        <div
            style={containerStyle}
            onKeyDown={handleKeyDown}
            onMouseDown={(e) => {
                // Close when clicking backdrop (mobile)
                if (isMobile && e.target === e.currentTarget) {
                    handleCancel();
                }
                e.stopPropagation();
            }}
            onTouchStart={(e) => e.stopPropagation()}
        >
            {/* The Card - Glass effect with premium shadows */}
            <div
                className="w-full max-w-[480px] glass-card rounded-[var(--radius-card)] border border-[var(--border-subtle)] shadow-[var(--shadow-float)] overflow-hidden"
                role="dialog"
                aria-label="Add Note"
                aria-busy={saving}
                onMouseDown={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-card)]">
                    <div className="flex items-center gap-2">
                        <StickyNote className="h-4 w-4 text-[var(--brand-solid)]" />
                        <span className="font-semibold text-sm text-[var(--text-primary)]">Add Note</span>
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleCancel}
                        disabled={saving}
                        className="h-7 w-7"
                        aria-label="Close"
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                {/* Content */}
                <div className="p-4 bg-[var(--bg-card)] space-y-4">
                    {/* Quote Block - Elegant left border accent */}
                    {quote && (
                        <div className="relative pl-3 py-2 border-l-2 border-[var(--brand-solid)] bg-[var(--bg-main)] rounded-r-lg">
                            <p className="text-xs text-[var(--text-secondary)] italic leading-relaxed max-h-20 overflow-y-auto">
                                "{quote}"
                            </p>
                        </div>
                    )}

                    {/* Textarea - Premium input styling */}
                    <textarea
                        ref={textareaRef}
                        className="w-full text-sm bg-[var(--bg-main)] border border-[var(--border-subtle)] rounded-[var(--radius-btn)] p-3 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-solid)] focus:border-transparent resize-none transition-all"
                        placeholder="Write your note here..."
                        value={content}
                        onChange={e => setContent(e.target.value)}
                        disabled={saving}
                        rows={4}
                    />

                    {error && <p role="alert" className="text-[var(--error)]">{error}</p>}
                    {/* Hint */}
                    <p className="text-xs text-[var(--text-tertiary)]">
                        Press <kbd className="px-1.5 py-0.5 text-[10px] bg-[var(--bg-main)] border border-[var(--border-subtle)] rounded font-mono">⌘ Enter</kbd> to save
                    </p>
                </div>

                {/* Footer - Actions */}
                <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[var(--border-subtle)] bg-[var(--bg-card)]">
                    <Button
                        variant="outline"
                        onClick={handleCancel}
                        disabled={saving}
                    >
                        Cancel
                    </Button>
                    <Button
                        variant="brand"
                        onClick={handleSubmit}
                        disabled={!content.trim() || saving}
                    >
                        Save Note
                    </Button>
                </div>
            </div>
        </div>
    );
}
