# Quick fix for width='stretch' compatibility
with open('ui/frontend.py', 'r', encoding='utf-8') as f:
    content = f.read()

original_count = content.count("width='stretch'")
content = content.replace("width='stretch'", "use_container_width=True")

with open('ui/frontend.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'✓ Replaced {original_count} instances of width="stretch" with use_container_width=True')
