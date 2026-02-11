#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUNDLE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK_DIR="/tmp/attractor-e2e-$$"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "========================================="
echo "Attractor E2E Tests"
echo "Working directory: $WORK_DIR"
echo "========================================="

PASS=0
FAIL=0

run_test() {
    local name="$1"
    local bundle="$2"
    local prompt="$3"
    local check="$4"
    
    echo ""
    echo "--- TEST: $name ---"
    local test_dir="$WORK_DIR/$name"
    mkdir -p "$test_dir"
    cd "$test_dir"
    
    if amplifier run -B "file://$bundle" --mode single "$prompt" 2>&1 | tee "$test_dir/output.log"; then
        if eval "$check"; then
            echo "PASS: $name"
            PASS=$((PASS + 1))
        else
            echo "FAIL: $name (check failed)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "FAIL: $name (amplifier run failed)"
        FAIL=$((FAIL + 1))
    fi
    cd "$WORK_DIR"
}

# E2E Test 1: Agent creates a file (Anthropic)
run_test "agent_file_creation" \
    "$BUNDLE_ROOT/profiles/attractor-e2e-anthropic.yaml" \
    "Create a file called hello.py that prints Hello World. Use the write_file tool." \
    "test -f hello.py && grep -qi hello hello.py"

# E2E Test 2: Agent reads and edits a file
mkdir -p "$WORK_DIR/agent_read_edit"
echo "print('original content')" > "$WORK_DIR/agent_read_edit/existing.py"
run_test "agent_read_edit" \
    "$BUNDLE_ROOT/profiles/attractor-e2e-anthropic.yaml" \
    "Read the file existing.py, then edit it to also print 'added line'. Use read_file then edit_file." \
    "grep -q 'original' existing.py && grep -q 'added' existing.py"

# E2E Test 3: Agent runs a shell command
run_test "agent_shell_exec" \
    "$BUNDLE_ROOT/profiles/attractor-e2e-anthropic.yaml" \
    "Run the command 'echo hello_from_shell' using the bash tool and tell me the output." \
    "grep -q 'hello_from_shell' output.log"

echo ""
echo "========================================="
echo "Results: $PASS passed, $FAIL failed"
echo "========================================="

exit $FAIL
