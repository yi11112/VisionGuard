$ErrorActionPreference='Stop'
$tools='C:\Users\22081\Documents\Codex\tools\visionguard'
$env:OLLAMA_MODELS=Join-Path $tools 'models\ollama'
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$env:OLLAMA_NUM_PARALLEL='1'
& "$tools\ollama\ollama.exe" serve

