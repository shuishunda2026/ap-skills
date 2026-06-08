@echo off
REM Sync aping skills from D:\PIproject\skills\ to pi agent dir under my-skills\.
REM Run this after editing any script.

set SRC=D:\PIproject\skills
set DST=C:\Users\shuis\.pi\agent\skills\ap-skills

for %%S in (aping-transcribing-audio aping-regrouping-srt aping-burning-subtitles aping-dubbing-video aping-segmenting-video aping-common) do (
    if exist "%SRC%\%%S" (
        echo [sync] %%S
        if exist "%DST%\%%S" rmdir /S /Q "%DST%\%%S"
        xcopy /E /I /Y /Q "%SRC%\%%S" "%DST%\%%S" >nul
    )
)

REM Also sync top-level docs to pi root
for %%F in (README.md NOTES.md) do (
    if exist "%SRC%\%%F" (
        echo [sync] %%F
        copy /Y "%SRC%\%%F" "%DST%\..\%%F" >nul
    )
)

echo.
echo [done] pi will pick up changes on next session.
