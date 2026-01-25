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

    local missing_sys=()
    local missing_pip=()

    command -v curl &> /dev/null || missing_sys+=("curl")
    command -v tmux &> /dev/null || missing_sys+=("tmux")
    command -v python3 &> /dev/null || missing_sys+=("python3")

    # Check Python modules
    if command -v python3 &> /dev/null; then
        if ! python3 -c "import requests" 2>/dev/null; then
            missing_pip+=("requests")
        fi
        if ! python3 -c "import ansi2html" 2>/dev/null; then
            missing_pip+=("ansi2html")
        fi
    fi

    local all_missing=("${missing_sys[@]}" "${missing_pip[@]}")

    if [ ${#all_missing[@]} -gt 0 ]; then
        warn "Missing dependencies:"
        [ ${#missing_sys[@]} -gt 0 ] && echo "  System: ${missing_sys[*]}"
        [ ${#missing_pip[@]} -gt 0 ] && echo "  Python: ${missing_pip[*]}"
        echo ""

        read -p "Install automatically? (Y/n): " auto_install

        if [[ ! "$auto_install" =~ ^[Nn]$ ]]; then
            # Install system packages
            if [ ${#missing_sys[@]} -gt 0 ]; then
                info "Installing system packages..."
                if command -v brew &> /dev/null; then
                    brew install "${missing_sys[@]}" && success "System packages installed" || warn "Some packages failed"
                elif command -v apt &> /dev/null; then
                    sudo apt update && sudo apt install -y "${missing_sys[@]}" && success "System packages installed" || warn "Some packages failed"
                else
                    warn "No package manager found (brew/apt). Install manually: ${missing_sys[*]}"
                fi
            fi

            # Install Python packages (--user installs to ~/.local, no system modification)
            if [ ${#missing_pip[@]} -gt 0 ]; then
                info "Installing Python packages to ~/.local..."
                if python3 -m pip install --user "${missing_pip[@]}" 2>/dev/null; then
                    success "Python packages installed"
                elif pip3 install --user "${missing_pip[@]}" 2>/dev/null; then
                    success "Python packages installed"
                else
                    warn "Could not install Python packages. Try manually:"
                    echo "  pip install --user ${missing_pip[*]}"
                fi
            fi

            # Re-verify
            echo ""
            info "Verifying installation..."
            local still_missing=()
            command -v curl &> /dev/null || still_missing+=("curl")
            command -v tmux &> /dev/null || still_missing+=("tmux")
            command -v python3 &> /dev/null || still_missing+=("python3")
            python3 -c "import requests" 2>/dev/null || still_missing+=("requests")
            python3 -c "import ansi2html" 2>/dev/null || still_missing+=("ansi2html")

            if [ ${#still_missing[@]} -gt 0 ]; then
                warn "Still missing: ${still_missing[*]}"
                read -p "Continue anyway? (y/N): " cont
                [[ ! "$cont" =~ ^[Yy]$ ]] && exit 1
            else
                success "All dependencies installed"
            fi
        else
            # Manual install instructions
            echo ""
            if [ ${#missing_pip[@]} -gt 0 ]; then
                echo "Install Python packages:"
                echo "  pip install --user ${missing_pip[*]}"
                echo ""
            fi
            if [ ${#missing_sys[@]} -gt 0 ]; then
                echo "Install system packages:"
                if command -v brew &> /dev/null; then
                    echo "  brew install ${missing_sys[*]}"
                elif command -v apt &> /dev/null; then
                    echo "  sudo apt install ${missing_sys[*]}"
                fi
                echo ""
            fi
            read -p "Continue anyway? (y/N): " cont
            [[ ! "$cont" =~ ^[Yy]$ ]] && exit 1
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
    local path_export='export PATH="$HOME/.local/bin:$PATH"'
    local shell_name=$(basename "$SHELL")
    local updated_files=()

    info "Configuring PATH for $shell_name..."

    case "$shell_name" in
        zsh)
            # zsh: add to .zshrc (interactive) and .zprofile (login shells on macOS)
            for rc_file in "$HOME/.zshrc" "$HOME/.zprofile"; do
                if ! grep -q '\.local/bin' "$rc_file" 2>/dev/null; then
                    # Ensure newline before appending
                    [ -f "$rc_file" ] && [ -n "$(tail -c1 "$rc_file")" ] && echo "" >> "$rc_file"
                    echo "$path_export" >> "$rc_file"
                    updated_files+=("$rc_file")
                fi
            done
            ;;
        bash)
            # bash: .bashrc for Linux, .bash_profile for macOS
            if [[ "$OSTYPE" == darwin* ]]; then
                local rc_file="$HOME/.bash_profile"
            else
                local rc_file="$HOME/.bashrc"
            fi
            if ! grep -q '\.local/bin' "$rc_file" 2>/dev/null; then
                [ -f "$rc_file" ] && [ -n "$(tail -c1 "$rc_file")" ] && echo "" >> "$rc_file"
                echo "$path_export" >> "$rc_file"
                updated_files+=("$rc_file")
            fi
            ;;
        fish)
            # fish: use fish_add_path
            local fish_config="$HOME/.config/fish/config.fish"
            mkdir -p "$(dirname "$fish_config")"
            if ! grep -q '\.local/bin' "$fish_config" 2>/dev/null; then
                [ -f "$fish_config" ] && [ -n "$(tail -c1 "$fish_config")" ] && echo "" >> "$fish_config"
                echo 'fish_add_path $HOME/.local/bin' >> "$fish_config"
                updated_files+=("$fish_config")
            fi
            ;;
        *)
            # Fallback: try common rc files
            for rc_file in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
                if [ -f "$rc_file" ] && ! grep -q '\.local/bin' "$rc_file" 2>/dev/null; then
                    [ -n "$(tail -c1 "$rc_file")" ] && echo "" >> "$rc_file"
                    echo "$path_export" >> "$rc_file"
                    updated_files+=("$rc_file")
                    break
                fi
            done
            ;;
    esac

    # Report what was updated
    if [ ${#updated_files[@]} -gt 0 ]; then
        for f in "${updated_files[@]}"; do
            success "Added ~/.local/bin to PATH in $f"
        done
    else
        success "PATH already configured"
    fi

    # Note: We can't modify the parent shell's PATH from a script.
    # The export below only affects this script's process.
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        export PATH="$HOME/.local/bin:$PATH"
        echo ""
        warn "PATH updated in shell configs, but current terminal needs refresh."
        echo "      Run: source ~/.${shell_name}rc"
        echo "      Or open a new terminal."
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

    create_sessions "$bot_token" "$chat_id"
}

# -----------------------------------------------------------------------------
# Create Session Config
# -----------------------------------------------------------------------------

create_single_session() {
    local bot_token="$1"
    local chat_id="$2"

    echo ""
    read -p "Session name: " session_name
    session_name=$(echo "$session_name" | tr -cd 'a-zA-Z0-9_-')

    if [ -z "$session_name" ]; then
        warn "Session name cannot be empty"
        return 1
    fi

    if [ -f "$CLAUDE_HOME/sessions/$session_name.conf" ]; then
        warn "Session '$session_name' already exists"
        read -p "Overwrite? (y/N): " overwrite
        [[ ! "$overwrite" =~ ^[Yy]$ ]] && return 1
    fi

    echo ""
    echo "Get Topic ID by sending a message in the topic,"
    echo "then running: get-topic-ids.sh --poll"
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

    return 0
}

create_sessions() {
    local bot_token="$1"
    local chat_id="$2"

    while true; do
        read -p "Create a session config? (y/N): " create_session

        if [[ "$create_session" =~ ^[Yy]$ ]]; then
            create_single_session "$bot_token" "$chat_id"
            echo ""
        else
            break
        fi
    done
}

# -----------------------------------------------------------------------------
# Add Sessions (for existing installations)
# -----------------------------------------------------------------------------

add_sessions() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Add Session Configs"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Load existing config
    if [ -f "$CLAUDE_HOME/telegram-remote.conf" ]; then
        source "$CLAUDE_HOME/telegram-remote.conf"
    fi

    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        warn "Global config not found or incomplete"
        echo "Run full setup first: ./setup-telegram-remote.sh --force"
        exit 1
    fi

    # Show existing sessions
    echo ""
    if [ -d "$CLAUDE_HOME/sessions" ] && [ "$(ls -A "$CLAUDE_HOME/sessions" 2>/dev/null)" ]; then
        info "Existing sessions:"
        for conf in "$CLAUDE_HOME/sessions"/*.conf; do
            [ -f "$conf" ] && echo "  - $(basename "$conf" .conf)"
        done
        echo ""
    fi

    create_sessions "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID"

    echo ""
    success "Done!"
}

# -----------------------------------------------------------------------------
# Check Existing Setup
# -----------------------------------------------------------------------------

check_existing_setup() {
    # Check if already set up
    if [ -f "$CLAUDE_HOME/telegram-remote.conf" ] && \
       [ -f "$CLAUDE_HOME/hooks/telegram-notify.sh" ] && \
       [ -f "$HOME/.local/bin/claude-remote" ]; then
        return 0  # Already set up
    fi
    return 1  # Not set up
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

show_completion() {
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
    echo "  # Add more session configs"
    echo "  ./setup-telegram-remote.sh"
    echo ""
    echo -e "${YELLOW}Note:${NC} Commands work in this terminal. For new terminals,"
    echo "      restart your shell or run: source ~/.$(basename "$SHELL")rc"
    echo ""
}

main() {
    banner

    # Always ensure PATH is configured (runs every time)
    update_path

    # Check for --force flag
    local force=false
    [[ "$1" == "--force" || "$1" == "-f" ]] && force=true

    # Check if already set up
    if ! $force && check_existing_setup; then
        success "Claude Remote is already installed"

        # Always update files to get latest versions
        info "Updating scripts and hooks..."
        install_files
        echo ""

        # Show existing sessions
        if [ -d "$CLAUDE_HOME/sessions" ] && [ "$(ls -A "$CLAUDE_HOME/sessions" 2>/dev/null)" ]; then
            info "Existing sessions:"
            for conf in "$CLAUDE_HOME/sessions"/*.conf; do
                [ -f "$conf" ] && echo "  - $(basename "$conf" .conf)"
            done
        else
            info "No session configs yet"
        fi

        echo ""
        echo "Options:"
        echo "  1) Add session configs"
        echo "  2) Re-run full setup (--force)"
        echo "  3) Exit"
        echo ""
        read -p "Choose [1-3]: " choice

        case "$choice" in
            1)
                add_sessions
                success "Done! Restart sessions to apply any script updates."
                ;;
            2)
                force=true
                ;;
            3)
                exit 0
                ;;
            *)
                exit 0
                ;;
        esac
    fi

    if $force || ! check_existing_setup; then
        check_dependencies
        install_files
        configure_hooks
        initial_config
        show_completion
    fi
}

main "$@"
