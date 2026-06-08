@echo off
REM Sync aping skills from D:\PIproject\skills\ to pi agent dir under ap-skills\.
REM Run this after editing any script.
REM Note: README.md is maintained manually in pi dir (not synced from D: drive).

set SRC=D:\PIproject\skills
set DST=C:\Users\shuis\.pi\agent\skills\ap-skills

for %%S in (aping-transcribing-audio aping-regrouping-srt aping-burning-subtitles aping-dubbing-video aping-segmenting-video aping-common) do (
    if exist "%SRC%\%%S" (
        echo [sync] %%S
        if exist "%DST%\%%S" rmdir /S /Q "%DST%\%%S"
        xcopy /E /I /Y /Q "%SRC%\%%S" "%DST%\%%S" >nul
    )
)

REM Sync NOTES.md (development notes, kept in both D: and pi)
if exist "%SRC%\NOTES.md" (
    echo [sync] NOTES.md
    copy /Y "%SRC%\NOTES.md" "%DST%\NOTES.md" >nul
)

echo.
echo [done] pi will pick up changes on next session.
echo [hint] README.md in pi dir is maintained manually, not synced.
