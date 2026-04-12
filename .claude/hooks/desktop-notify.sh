#!/bin/bash
# =============================================================================
# Desktop Notify Hook
# Sends a macOS/Linux desktop notification when a session ends.
# Runs as a Stop hook.
# =============================================================================

LOG_FILE=".claude/hooks/hooks.log"
HOOK_NAME="desktop-notify"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$HOOK_NAME] [$1] $2" >> "$LOG_FILE" 2>/dev/null
}

PROJECT=$(basename "$(pwd)" | tr -d '"\\')
SESSION_DATE=$(date '+%H:%M')

# Count uncommitted changes as a quick status indicator
UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

if [ "$UNCOMMITTED" -gt 0 ]; then
    STATUS_MSG="$UNCOMMITTED uncommitted change(s)"
else
    STATUS_MSG="Working tree clean"
fi

TITLE="Claude Code — $PROJECT"
MESSAGE="Session ended at $SESSION_DATE. $STATUS_MSG."

# macOS notification
if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v osascript &>/dev/null; then
        # Escape double quotes and backslashes before embedding in AppleScript string
        SAFE_TITLE=$(printf '%s' "$TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')
        SAFE_MSG=$(printf '%s' "$MESSAGE" | sed 's/\\/\\\\/g; s/"/\\"/g')
        osascript -e "display notification \"$SAFE_MSG\" with title \"$SAFE_TITLE\"" 2>/dev/null &
        log "INFO" "macOS notification sent: $MESSAGE"
    fi
fi

# Linux notification (if notify-send available)
if [[ "$OSTYPE" == "linux"* ]]; then
    if command -v notify-send &>/dev/null; then
        notify-send "$TITLE" "$MESSAGE" --icon=dialog-information 2>/dev/null &
        log "INFO" "Linux notification sent: $MESSAGE"
    fi
fi

# WSL: use PowerShell toast notification
# Sanitize values before embedding in PowerShell string (strip single quotes which would break the template)
if grep -qi "microsoft" /proc/version 2>/dev/null; then
    if command -v powershell.exe &>/dev/null; then
        SAFE_PS_TITLE=$(printf '%s' "$TITLE" | tr -d "'" | cut -c1-128)
        SAFE_PS_MSG=$(printf '%s' "$MESSAGE" | tr -d "'" | cut -c1-256)
        powershell.exe -Command "
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        \$Template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        \$Text = \$Template.GetElementsByTagName('text')
        \$Text[0].AppendChild(\$Template.CreateTextNode('$SAFE_PS_TITLE')) | Out-Null
        \$Text[1].AppendChild(\$Template.CreateTextNode('$SAFE_PS_MSG')) | Out-Null
        \$Notification = [Windows.UI.Notifications.ToastNotification]::new(\$Template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code').Show(\$Notification)
        " 2>/dev/null &
        log "INFO" "WSL notification sent"
    fi
fi

exit 0
