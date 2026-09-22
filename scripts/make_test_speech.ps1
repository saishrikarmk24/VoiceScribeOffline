# Synthesises one WAV per turn of a spoken clinical encounter, for verifying the
# real recording -> transcription -> note pipeline. The turns are joined into a
# single recording by scripts/make_test_speech.py, which owns the WAV container
# handling (SAPI writes an 18-byte fmt chunk, so headers are not a fixed size).
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/make_test_speech.ps1 <outputDir>

param(
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Add-Type -AssemblyName System.Speech

$turns = @(
    @{ Voice = 'Microsoft Hazel Desktop'; Text = 'Good afternoon, I am Doctor Whitfield. What has brought you in today?' },
    @{ Voice = 'Microsoft Zira Desktop';  Text = 'Patient reports a new headache for the past three days with mild nausea.' },
    @{ Voice = 'Microsoft Hazel Desktop'; Text = 'Have you noticed any visual disturbance or vomiting alongside the nausea?' },
    @{ Voice = 'Microsoft Zira Desktop';  Text = 'No vomiting at all, but bright light makes the headache noticeably worse.' },
    @{ Voice = 'Microsoft Hazel Desktop'; Text = 'I will arrange a neurological examination and we will review your blood pressure.' }
)

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$index = 0
foreach ($turn in $turns) {
    $path = Join-Path $OutputDir ("turn_{0:d2}.wav" -f $index)
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $synth.SelectVoice($turn.Voice)
        $synth.Rate = -1
        $synth.SetOutputToWaveFile($path)
        $synth.Speak($turn.Text)
    }
    finally {
        $synth.Dispose()
    }
    Write-Output $path
    $index += 1
}
