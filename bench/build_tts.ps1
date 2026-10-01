param([string]$OutDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "audio"))
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$ru = "Сегодня я тестирую локальную диктовку на своём компьютере. Приложение должно распознавать русскую речь без интернета и вставлять готовый текст прямо в активное поле. Сейчас мы проверим скорость работы и качество распознавания на обычном четырёхъядерном процессоре."
$en = "Today I am testing local dictation on my computer. The application should recognize English speech without an internet connection and insert the finished text directly into the active field. Now we will measure the speed and the accuracy on a regular quad core processor."

function Say([string]$Text, [string]$Voice, [string]$File, [int]$Rate = 0) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($Voice)
  $s.Rate = $Rate
  $s.SetOutputToWaveFile($File)
  $s.Speak($Text)
  $s.Dispose()
  $len = (New-Object System.IO.FileInfo($File)).Length
  Write-Output ("{0}  ->  {1} bytes" -f (Split-Path $File -Leaf), $len)
}

Say $ru "Microsoft Irina Desktop" "$OutDir\ru_short.wav"
Say ("{0} {0} {0}" -f $ru) "Microsoft Irina Desktop" "$OutDir\ru_long.wav"
Say $en "Microsoft Zira Desktop" "$OutDir\en_short.wav"
Say ("{0} {0}" -f $en) "Microsoft Zira Desktop" "$OutDir\en_long.wav"
