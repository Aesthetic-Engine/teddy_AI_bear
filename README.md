# Teddy AI Bear Runtime

Local runtime code for Teddy, an embodied AI teddy bear inspired by *A.I. Artificial Intelligence*.

This repository is intentionally source-focused. It does not include private conversation history, local memory databases, generated audio artifacts, legacy project archives, or licensed voice assets.

## What You Need

### Core Software

- Windows 10 or Windows 11, 64-bit
- Python 3.10+
- an `OPENAI_API_KEY` for the live language model path
- a compatible local Piper installation and voice model
- local STT model assets for `vosk` and `faster-whisper`
- local Rhubarb lip-sync binaries if you want viseme-based mouth movement

### Recommended System Specs

- CPU: modern 6-core or better desktop CPU
- RAM: 32 GB recommended
- GPU: NVIDIA RTX 3060 or better, with CUDA support
- VRAM: 8 GB minimum, 12 GB preferred
- Storage: at least 15 GB free for models, tools, and runtime files
- Audio: USB omnidirectional microphone plus speakers or powered audio output

### Minimum Practical System Specs

- CPU: modern 4-core CPU
- RAM: 16 GB
- GPU: NVIDIA GPU with CUDA support strongly recommended
- VRAM: 6 to 8 GB can work for a lighter setup, but with less headroom
- Storage: at least 10 GB free

### Notes On Performance

- Teddy was developed on a Windows desktop with an RTX 4070, and that class of machine gives a much smoother experience.
- The biggest local performance win comes from GPU-accelerated `faster-whisper` speech recognition.
- Teddy can still function on weaker hardware, but wake-to-response time and speech recognition speed will degrade.
- This project does not rely on a local LLM for normal operation, so GPU demand is much lower than many fully local assistants.

### Core Hardware

### Electronics

- 1 omnidirectional microphone ([example](https://a.co/d/0ci3ykjY))
- 1 speaker or powered external speakers ([example](https://a.co/d/0hOwwwmK))
- 1 servo for the mouth ([recommended example](https://a.co/d/0an8Dm1F))
- 1 Arduino Nano with USB cable ([example](https://a.co/d/093dZeSg))
- 1 PCA9685 servo driver board ([example](https://a.co/d/02bqGY7G))
- jumper wires ([example](https://a.co/d/01hd0aUA))
- a suitable power supply for the servo and controller ([example](https://a.co/d/035LAYj1))

### Mechanical Parts

- 1 plush bear body
- a simple jaw linkage or lever mechanism that the servo can pull ([example](https://a.co/d/0i4UEZzq))
- a small sheet of aluminum for the internal bracket and mounting structure ([example](https://a.co/d/0j51v3tu))
- a small hinge to act as the jaw pivot ([example](https://a.co/d/0eMDf472))
- wire for connecting the servo horn to the hinge or linkage ([example](https://a.co/d/09qTHPsB))
- a small amount of pink felt for simple lower gums
- a project box for the Nano and PCA9685 if you want cleaner cable management (optional) ([example](https://a.co/d/0hPVt5Gm))

### Basic Tools

- small screwdrivers
- pliers
- wire cutters
- scissors or a hobby knife
- sewing needle and thread
- glue suitable for fabric and small mechanical parts
- something to mark cut lines before opening the bear

## Bear Recommendation

If you want the closest physical base to the bear used in this project, search eBay, Mercari, Etsy, and similar secondhand marketplaces for **Super Toy Teddy by Tiger**. Used ones often land around the `$130-$180` range when they appear. Example listing: https://www.ebay.com/itm/298050392087

A practical starting approach is to make one clean vertical access slice through the back of the head so you can install the servo and jaw assembly with minimal visible damage from the front.

You will also need to open the mouth, attach the jaw piece to the bottom lip, and add a little pink felt along the lower lip as simple gums that cover the hinge. Teddy does not open especially wide, so this part can stay fairly minimal. Do not overbuild the mouth range.

## Mechanical Build Guide

> If this is your first animatronic build, take inventory of your tools and parts before cutting anything. Test-fit each part before gluing or sewing the bear closed.

### 1. Inspect the bear

Check how the head is stuffed and where the lower mouth area can move naturally.

Your goal is not a huge jaw swing. Your goal is a small, believable lower-lip movement.

### 2. Open the head from the back

Make one clean cut through the back of the head so you can reach the inside of the face.

Try to keep the opening just large enough to install and service the mechanism.

### 3. Open the mouth

Carefully cut open the mouth area at the seam or natural mouth line.

You only need enough room to let the lower lip and jaw section move. Keep this conservative.

### 4. Build the internal jaw enclosure

Cut the aluminum sheet down to size so it can fit inside the head behind the mouth.

This plate acts as the base for the jaw assembly. Screw the bracket to the center of the plate. Mount the servo to one end of the bracket and mount the hinge to the other end.

The hinge is the moving jaw piece. The servo does not open the mouth directly. Instead, the servo pulls the hinge upward through a simple wire or linkage.

If needed, bend or wrap the aluminum plate slightly so it sits cleanly inside the head and also helps keep stuffing away from the moving parts.

### 5. Mount the servo

Attach the servo to the bracket.

Make sure the servo horn has a clear path to pull the jaw linkage without rubbing heavily on stuffing or fabric.

Before moving on, check that the servo can rotate through the intended range without binding.

### 6. Mount the hinge

Attach the hinge so it can act as the pivoting lower jaw.

One side of the hinge should be fixed to the bracket structure. The other side should remain free to move upward when the servo pulls it.

The hinge is what creates the actual mouth-opening motion.

### 7. Connect the servo to the jaw linkage

Use wire or a simple linkage to connect the servo horn to the free-moving side of the hinge. You can loop the wire through a hole in the hinge and twist it securely or solder it if that fits your build.

The servo should pull the hinge upward rather than force the whole mouth outward.

Keep the linkage simple. Small motion is enough.

### 8. Attach the jaw to the mouth

Position the mechanism inside the head and test-fit it before gluing.

Once you are sure the geometry works, glue the moving jaw piece to the bottom lip so the lower mouth rises when the hinge is pulled.

This is the most important fit check in the build. If the lip attachment point is wrong, the mouth will look weak or unnatural.

### 9. Add the gums

Glue a small strip of pink felt along the lower lip and jaw area to create simple gums and hide some of the mechanism.

Because Teddy does not open very wide, you usually do not need much more than this.

### 10. Protect the mechanism from stuffing

Use the aluminum bracket shape and felt placement to keep stuffing from getting pulled into the hinge or linkage.

Before closing the head, make sure no loose fabric or stuffing catches when the jaw moves.

## Wiring Overview

### 1. Servo to PCA9685

Wire the mouth servo to channel `0` on the PCA9685.

### 2. PCA9685 to Arduino Nano

Connect the PCA9685 control lines and power as required by your Arduino setup.

### 3. Arduino Nano to host PC

Connect the Nano to the host PC over USB so Teddy can send mouth commands through the bridge.

### 4. External power

Use a proper power source for the servo and controller. Do not assume the Nano alone should carry the full mouth-load current.

### Safety and heat note

Only the servo should live inside the bear. Keep the Arduino Nano, PCA9685, and power supply outside the plush body, ideally inside a small project box. Run the power from the wall to that box, then route only the necessary wiring into the bear.

Make sure your wiring is insulated, strain-relieved, and not buried in polyester fill. Plush bodies trap heat and can snag moving parts, so do not smother electronics inside the stuffing.

## Tuning the Jaw

### 1. Bench test before sewing

Do not sew the head closed yet.

Manually move the jaw and then power the servo at a safe range first. You want to confirm:

- the mouth closes fully
- the mouth opens enough to read on camera
- nothing strains or catches
- the lip attachment holds

### 2. Upload the Arduino sketch

Use the Arduino IDE to upload your mouth-control sketch to the Nano.

Tune closed position first, then open position, then repeated motion.

### 3. Tune for realism, not maximum travel

Do not aim for the widest possible opening. Aim for the best-looking opening that does not strain the mechanism.

If the mouth is opening too wide or closing too tightly, you will usually hear the servo strain.

Teddy's mouth only needs a modest range to read well.

### 4. Final closure

Once the jaw movement is working the way you want, tuck the stuffing back into place carefully and sew the back of the head closed.

Try to keep the closure serviceable enough that you can reopen it later if you need to retune or repair the jaw.

## Common Mistakes

- cutting a larger opening than you really need
- gluing the jaw to the bottom lip before test-fitting the geometry
- letting stuffing catch in the linkage or hinge
- tuning for maximum opening instead of believable motion
- powering the servo poorly and then chasing what looks like a software problem
- sewing the head shut before you have confirmed full close, safe open, and repeated clean movement

## Software Architecture

Teddy's public runtime is a local voice pipeline wrapped around a cloud LLM:

1. `Vosk` listens for the wake phrase.
2. `faster-whisper` transcribes the user's speech.
3. Teddy builds prompt context from the workspace files, recent turns, and local memory.
4. `OpenAI gpt-5.4-mini` generates Teddy's reply.
5. `Piper` synthesizes the reply into speech audio.
6. `Rhubarb` can generate viseme timing from the spoken audio.
7. The mouth bridge sends angle commands to the Arduino Nano.
8. The Arduino drives the PCA9685, which drives the mouth servo.

In short, the loop is:

`Wake detection -> STT -> prompt assembly -> OpenAI reply -> Piper TTS -> optional viseme timing -> mouth bridge -> Arduino Nano -> PCA9685 -> servo`

## AI-Assisted Customization

If you want Cursor, Claude Code, Codex, or another coding agent to customize Teddy for you, point it at `CUSTOMIZE_TEDDY_WITH_AI.md`. That file tells the assistant which questions to ask and which workspace files to update.

## Set Your Name

Run `Set-TeddyUserProfile.ps1` from the repo root to set your name and the name Teddy should call you. The script updates `workspace/USER.md`, which Teddy uses as part of his prompt context.

If you prefer manual setup, you can still edit `workspace/USER.md` directly.

## Quick Start

1. Run `Set-TeddyUserProfile.ps1` from the repo root and fill in your name.
2. Make sure your local TTS, STT, and any lip-sync dependencies are installed.
3. Run `Start-Teddy.bat` from the repo root.

`Start-Teddy.bat` is the easiest launcher for normal use. It calls `Start-Teddy.ps1`, which starts Teddy in auto-listen mode and attempts to bring up the local helper services Teddy expects, including speech and mouth support where available.

If you want more control, you can run `Start-Teddy.ps1` directly with your own flags.

## Voice Setup

This repo does not redistribute Teddy's current voice model.

For local TTS voices:
- Piper releases: https://github.com/rhasspy/piper/releases
- Piper voice list: https://github.com/rhasspy/piper/blob/master/VOICES.md

For stronger Fallout-style voice options, install Mantella for Fallout 4 and browse the Piper voice models in `F4SE\Plugins\MantellaSoftware\piper\models\fallout4`:
- Mantella Fallout 4 download: https://www.nexusmods.com/Core/Libs/Common/Widgets/ModRequirementsPopUp?id=309019&game_id=1151
- Mantella project page: https://github.com/art-from-the-machine/Mantella

If you want the closest approximation to Teddy's current voice, start by trying `fallout4-dlc01robotcompanionmaledefault`.

## Not Included

This repository does not include:

- prior Teddy conversations and memory state
- temporary and generated runtime artifacts
- licensed or machine-local voice/model files
- private archive folders and historical working material
- your own local runtime data such as memory databases, cache files, and generated audio

## Repository Scope

This repo is meant to publish Teddy's runtime code and prompt structure, not a personal runtime snapshot.

## Current Workspace Layout

- `runtime/` main runtime code
- `bridge/` mouth bridge and hardware helpers
- `grading/` automated grading harness
- `workspace/` Teddy identity and prompt files
- `prompts/` small prompt templates used by the runtime

## Notes

The current runtime is built around Teddy's existing local voice path. Voice assets are intentionally not redistributed here.
