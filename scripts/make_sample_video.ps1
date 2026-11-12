# Builds a ~3-minute synthetic "podcast" test video with real speech (Windows SAPI TTS, free)
# Usage: powershell -File scripts/make_sample_video.ps1 [-Out sample.mp4]
param([string]$Out = "$PSScriptRoot\..\samples\sample_podcast.mp4")

Add-Type -AssemblyName System.Speech
$dir = Split-Path -Parent $Out
New-Item -ItemType Directory -Force $dir | Out-Null
$wav = Join-Path $dir "sample_podcast.wav"

$lines = @(
  @(0, "Welcome back to the Build Notes podcast. Today we're talking about how small teams ship products fast."),
  @(1, "Thanks for having me. I've been building software for about twelve years now."),
  @(0, "So let's start with the obvious question. Why do most side projects never launch?"),
  @(1, "Here's the truth. Most people spend ninety percent of their time on features nobody asked for. They polish the logo, they rewrite the backend twice, and they never talk to a single customer."),
  @(0, "That hurts a little, because I have done exactly that."),
  @(1, "We all have! My first startup burned through forty thousand dollars before we had one paying user. That was the most painful lesson of my career."),
  @(0, "Wow. What would you do differently today?"),
  @(1, "I would launch in two weeks, not two years. Write a landing page, put a price on it, and see if anyone pays. If nobody pays, you just saved yourself a year."),
  @(0, "Okay, but what about quality? Doesn't shipping fast mean shipping broken software?"),
  @(1, "No, and this is the mistake I see everywhere. Fast does not mean careless. It means small. You ship one feature that works perfectly instead of ten features that half work."),
  @(0, "I love that. One feature that works perfectly."),
  @(1, "Exactly. And then you listen. Your users will tell you what to build next, every single week, for free."),
  @(0, "Let's talk about burnout. You mentioned you almost quit at one point."),
  @(1, "Honestly, I cried in my car after a demo went wrong in front of our biggest client. I thought the company was over. My co founder sat with me and said, we fix it tonight, and we did."),
  @(0, "That's a powerful story. What did you learn from that night?"),
  @(1, "That a team is not the people who are there when things go well. It's the people who stay when everything breaks."),
  @(0, "Before we wrap up, give our listeners three practical tips."),
  @(1, "Number one, talk to five customers this week. Number two, cut your feature list in half. Number three, set a launch date and tell someone, so you can't hide."),
  @(0, "Talk to customers, cut features, and set a date. That's incredibly clear. Thank you so much for coming on."),
  @(1, "Thank you. And to everyone listening, stop waiting. Ship the thing!")
)

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
$v0 = $voices[0]; $v1 = if ($voices.Count -gt 1) { $voices[1] } else { $voices[0] }
$pb = New-Object System.Speech.Synthesis.PromptBuilder
foreach ($l in $lines) {
  $pb.StartVoice($(if ($l[0] -eq 0) { $v0 } else { $v1 }))
  $pb.AppendText($l[1])
  $pb.EndVoice()
  $pb.AppendBreak([TimeSpan]::FromMilliseconds(700))
}
$synth.SetOutputToWaveFile($wav)
$synth.Speak($pb)
$synth.Dispose()

$ff = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ff) { $ff = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName }
# Two "speakers" on a studio-like backdrop with gentle motion so scene/motion signals have something to read.
$vf = "color=c=0x1d1b2e:s=1920x1080:r=30,drawbox=x=260:y=300:w=520:h=520:color=0x8b5cf6@0.9:t=fill,drawbox=x=1140:y=300:w=520:h=520:color=0x22d3ee@0.9:t=fill,drawbox=x='260+40*sin(t)':y=860:w=520:h=24:color=white@0.6:t=fill"
& $ff -y -v error -f lavfi -i $vf -i $wav -shortest -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p -c:a aac -b:a 128k $Out
Remove-Item $wav
Write-Output "Wrote $Out"
