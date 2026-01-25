#!/bin/bash
# =============================================================================
# setup-telegram-remote.sh - Install Claude Remote (Multi-Session)
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

banner() {
    echo -e "${CYAN}"
    echo "═══════════════════════════════════════════════════════════"
    echo "       Claude Remote - Multi-Session Telegram Setup        "
    echo "═══════════════════════════════════════════════════════════"
    echo -e "${NC}"
}

info()    { echo -e "${BLUE}►${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}!${NC} $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }

# -----------------------------------------------------------------------------
# Check Dependencies
# -----------------------------------------------------------------------------

check_dependencies() {
    info "Checking dependencies..."
    
    local missing=()
    
    command -v curl &> /dev/null || missing+=("curl")
    command -v tmux &> /dev/null || missing+=("tmux")
    command -v python3 &> /dev/null || missing+=("python3")
    
    # Check Python modules
    if command -v python3 &> /dev/null; then
        if ! python3 -c "import requests" 2>/dev/null; then
            missing+=("python3-requests")
        fi
        if ! python3 -c "import ansi2html" 2>/dev/null; then
            missing+=("python3-ansi2html")
        fi
    fi
    
    if [ ${#missing[@]} -gt 0 ]; then
        warn "Missing dependencies: ${missing[*]}"
        echo ""
        
        if [[ " ${missing[*]} " =~ "python3-requests" ]] || [[ " ${missing[*]} " =~ "python3-ansi2html" ]]; then
            echo "Install Python modules with:"
            if [[ " ${missing[*]} " =~ "python3-requests" ]]; then
                echo "  pip install requests --break-system-packages"
            fi
            if [[ " ${missing[*]} " =~ "python3-ansi2html" ]]; then
                echo "  pip install ansi2html --break-system-packages"
            fi
            echo ""
        fi
        
        local pkg_missing=()
        for dep in "${missing[@]}"; do
            [[ "$dep" != "python3-requests" && "$dep" != "python3-ansi2html" ]] && pkg_missing+=("$dep")
        done
        
        if [ ${#pkg_missing[@]} -gt 0 ]; then
            echo "Install system packages with:"
            if command -v apt &> /dev/null; then
                echo "  sudo apt install ${pkg_missing[*]}"
            elif command -v brew &> /dev/null; then
                echo "  brew install ${pkg_missing[*]}"
            fi
        fi
        
        echo ""
        read -p "Continue anyway? (y/N): " cont
        if [[ ! "$cont" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        success "All dependencies installed"
    fi
}

# -----------------------------------------------------------------------------
# Install Files
# -----------------------------------------------------------------------------

install_files() {
    info "Installing files..."
    
    # Create directories
    mkdir -p "$CLAUDE_HOME/hooks"
    mkdir -p "$CLAUDE_HOME/commands"
    mkdir -p "$CLAUDE_HOME/sessions"
    mkdir -p "$CLAUDE_HOME/pids"
    mkdir -p "$CLAUDE_HOME/logs"
    mkdir -p "$HOME/.local/bin"
    
    # Install hooks
    for hook in telegram-notify.sh telegram-listener.py telegram-preview.sh remote-notify.sh; do
        if [ -f "$SCRIPT_DIR/hooks/$hook" ]; then
            cp "$SCRIPT_DIR/hooks/$hook" "$CLAUDE_HOME/hooks/"
            chmod +x "$CLAUDE_HOME/hooks/$hook"
            success "Installed hooks/$hook"
        fi
    done
    
    # Install commands
    for cmd in "$SCRIPT_DIR"/commands/*.md; do
        if [ -f "$cmd" ]; then
            cp "$cmd" "$CLAUDE_HOME/commands/"
            success "Installed commands/$(basename "$cmd")"
        fi
    done
    
    # Install launchers
    if [ -f "$SCRIPT_DIR/claude-remote" ]; then
        cp "$SCRIPT_DIR/claude-remote" "$HOME/.local/bin/"
        chmod +x "$HOME/.local/bin/claude-remote"
        success "Installed claude-remote"
    fi
    
    # Install helper scripts
    if [ -f "$SCRIPT_DIR/get-topic-ids.sh" ]; then
        cp "$SCRIPT_DIR/get-topic-ids.sh" "$HOME/.local/bin/"
        chmod +x "$HOME/.local/bin/get-topic-ids.sh"
        success "Installed get-topic-ids.sh"
    fi
    
    # Copy claude-notify from v1 if exists or create simple version
    if [ -f "$SCRIPT_DIR/claude-notify" ]; then
        cp "$SCRIPT_DIR/claude-notify" "$HOME/.local/bin/"
        chmod +x "$HOME/.local/bin/claude-notify"
        success "Installed claude-notify"
    else
        # Create simple claude-notify
        cat > "$HOME/.local/bin/claude-notify" << 'NOTIFY_SCRIPT'
#!/bin/bash
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
FLAG_FILE="$CLAUDE_HOME/notifications-enabled"

case "${1:-}" in
    on)
        touch "$FLAG_FILE"
        echo "✓ Notifications enabled"
        ;;
    off)
        rm -f "$FLAG_FILE"
        echo "✓ Notifications disabled"
        ;;
    *)
        if [ -f "$FLAG_FILE" ]; then
            echo "Notifications: enabled"
        else
            echo "Notifications: disabled"
        fi
        echo "Usage: claude-notify [on|off]"
        ;;
esac
NOTIFY_SCRIPT
        chmod +x "$HOME/.local/bin/claude-notify"
        success "Created claude-notify"
    fi
    
    # Enable notifications by default
    touch "$CLAUDE_HOME/notifications-enabled"
}

# -----------------------------------------------------------------------------
# Configure Claude Code Hooks
# -----------------------------------------------------------------------------

configure_hooks() {
    info "Configuring Claude Code hooks..."
    
    local settings_file="$CLAUDE_HOME/settings.json"
    
    # Check if hooks already configured
    if [ -f "$settings_file" ]; then
        if grep -q "telegram-notify" "$settings_file" 2>/dev/null; then
            info "Hooks already configured in settings.json"
            return
        fi
    fi
    
    # If settings.json exists, we need to merge; otherwise create new
    if [ -f "$settings_file" ]; then
        # Backup existing settings
        cp "$settings_file" "$settings_file.backup"
        info "Backed up existing settings to settings.json.backup"
        
        # Use Python to merge hooks into existing settings
        SETTINGS_PATH="$settings_file" python3 << 'MERGE_SCRIPT'
import json
import os

settings_path = os.environ['SETTINGS_PATH']

# New hooks to add
new_hooks = {
    "Notification": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": "~/.claude/hooks/telegram-notify.sh notification --session ${CLAUDE_SESSION:-default}",
                    "timeout": 10
                }
            ]
        }
    ],
    "Stop": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": "~/.claude/hooks/telegram-notify.sh complete --session ${CLAUDE_SESSION:-default}",
                    "timeout": 10
                }
            ]
        }
    ]
}

try:
    with open(settings_path, 'r') as f:
        settings = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    settings = {}

# Merge hooks
if 'hooks' not in settings:
    settings['hooks'] = {}

for hook_type, hook_config in new_hooks.items():
    if hook_type not in settings['hooks']:
        settings['hooks'][hook_type] = hook_config
    else:
        # Append to existing hooks if telegram-notify not already present
        existing = settings['hooks'][hook_type]
        has_telegram = any('telegram-notify' in str(h) for h in existing)
        if not has_telegram:
            settings['hooks'][hook_type].extend(hook_config)

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)

print("Hooks merged successfully")
MERGE_SCRIPT
        
        if [ $? -eq 0 ]; then
            success "Claude Code hooks merged into existing settings"
        else
            warn "Could not merge hooks. Restoring backup..."
            mv "$settings_file.backup" "$settings_file"
            return 1
        fi
    else
        # Create new settings file
        cat > "$settings_file" << 'SETTINGS'
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/telegram-notify.sh notification --session ${CLAUDE_SESSION:-default}",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/telegram-notify.sh complete --session ${CLAUDE_SESSION:-default}",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
SETTINGS
        success "Claude Code hooks configured"
    fi
}

# -----------------------------------------------------------------------------
# Update PATH
# -----------------------------------------------------------------------------

update_path() {
    local shell_rc=""
    
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        shell_rc="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        shell_rc="$HOME/.bashrc"
    fi
    
    if [ -n "$shell_rc" ]; then
        if ! grep -q '\.local/bin' "$shell_rc" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_rc"
            success "Added ~/.local/bin to PATH in $shell_rc"
            warn "Run: source $shell_rc"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Initial Configuration
# -----------------------------------------------------------------------------

initial_config() {
    echo ""
    echo "Would you like to configure Telegram now?"
    read -p "(Y/n): " do_config
    
    if [[ "$do_config" =~ ^[Nn]$ ]]; then
        return
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Telegram Configuration"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    echo "1. Create a bot with @BotFather on Telegram"
    echo "2. Get the bot token"
    echo ""
    echo -e "${YELLOW}Important:${NC} If using a group, disable Bot Privacy Mode:"
    echo "   @BotFather → /mybots → [your bot] → Bot Settings → Group Privacy → Disable"
    echo ""
    read -p "Bot Token: " bot_token
    
    # Validate bot token is not empty
    if [ -z "$bot_token" ]; then
        error "Bot token is required"
    fi
    
    echo ""
    echo "For multi-session with Topics:"
    echo "  - Create a Telegram Group"
    echo "  - Add your bot as admin"
    echo "  - Enable Topics in group settings"
    echo "  - Use Group ID (negative, like -1001234567890)"
    echo ""
    echo "For single session:"
    echo "  - Use your personal Chat ID (positive)"
    echo "  - Message @userinfobot to get it"
    echo ""
    read -p "Chat/Group ID: " chat_id
    
    # Save global config
    cat > "$CLAUDE_HOME/telegram-remote.conf" << EOF
# Claude Remote - Global Configuration
TELEGRAM_BOT_TOKEN="$bot_token"
TELEGRAM_CHAT_ID="$chat_id"
EOF
    
    chmod 600 "$CLAUDE_HOME/telegram-remote.conf"
    success "Global config saved"
    
    # Test connection
    echo ""
    read -p "Send test message? (Y/n): " test_msg
    
    if [[ ! "$test_msg" =~ ^[Nn]$ ]]; then
        local response=$(curl -s -X POST "https://api.telegram.org/bot$bot_token/sendMessage" \
            -d "chat_id=$chat_id" \
            --data-urlencode "text=🚀 Claude Remote installed successfully!" \
            2>&1)
        
        if echo "$response" | grep -q '"ok":true'; then
            success "Test message sent!"
        else
            warn "Test failed. Check credentials."
            echo "Response: $response"
        fi
    fi
    
    # Ask about multi-session
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Multi-Session Setup (Optional)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "If you're using a Forum group with Topics,"
    echo "you can create per-session configs now."
    echo ""
    read -p "Create a session config? (y/N): " create_session
    
    if [[ "$create_session" =~ ^[Yy]$ ]]; then
        echo ""
        read -p "Session name: " session_name
        session_name=$(echo "$session_name" | tr -cd 'a-zA-Z0-9_-')
        
        echo ""
        echo "Get Topic ID by sending a message in the topic,"
        echo "then running: get-topic-ids.sh"
        echo "(Leave empty to configure later)"
        read -p "Topic ID: " topic_id
        
        mkdir -p "$CLAUDE_HOME/sessions"
        cat > "$CLAUDE_HOME/sessions/$session_name.conf" << EOF
# Claude Remote - Session: $session_name
TELEGRAM_BOT_TOKEN="$bot_token"
TELEGRAM_CHAT_ID="$chat_id"
TELEGRAM_TOPIC_ID="$topic_id"
TMUX_SESSION="claude-$session_name"
EOF
        
        chmod 600 "$CLAUDE_HOME/sessions/$session_name.conf"
        success "Session '$session_name' configured"
        
        if [ -n "$topic_id" ]; then
            # Test with topic
            local response=$(curl -s -X POST "https://api.telegram.org/bot$bot_token/sendMessage" \
                -d "chat_id=$chat_id" \
                -d "message_thread_id=$topic_id" \
                --data-urlencode "text=🚀 [$session_name] Session configured!" \
                2>&1)
            
            if echo "$response" | grep -q '"ok":true'; then
                success "Test message sent to topic!"
            fi
        fi
    fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    banner
    
    check_dependencies
    install_files
    configure_hooks
    update_path
    initial_config
    
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                    Installation Complete!                  ${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Quick Start:"
    echo ""
    echo "  # Start default session"
    echo "  claude-remote"
    echo ""
    echo "  # Start named session"
    echo "  claude-remote myproject"
    echo ""
    echo "  # Create new session with topic"
    echo "  claude-remote --new"
    echo ""
    echo "  # List sessions"
    echo "  claude-remote --list"
    echo ""
    echo "  # Get topic IDs from your group"
    echo "  get-topic-ids.sh"
    echo ""
}

main "$@"
