on run argv
    set playlistName to "Codex Monday Morning Queue"
    set csvPath to missing value
    set shouldPlay to true
    set minScore to 90
    set minScoreSetByUser to false
    set strictMode to true

    set i to 1
    repeat while i ≤ (count of argv)
        set arg to item i of argv
        if arg is "--playlist" then
            set i to i + 1
            if i ≤ (count of argv) then set playlistName to item i of argv
        else if arg is "--csv" then
            set i to i + 1
            if i ≤ (count of argv) then set csvPath to item i of argv
        else if arg is "--no-play" then
            set shouldPlay to false
        else if arg is "--loose" then
            set strictMode to false
        else if arg is "--strict" then
            set strictMode to true
        else if arg is "--min-score" then
            set i to i + 1
            if i ≤ (count of argv) then
                set minScore to (item i of argv) as integer
                set minScoreSetByUser to true
            end if
        end if
        set i to i + 1
    end repeat

    if csvPath is missing value then error "Missing required argument: --csv /path/to/file.csv"
    if (not strictMode) and (not minScoreSetByUser) then set minScore to 70

    set trackSpecs to my loadTracksFromCSV(csvPath)
    if (count of trackSpecs) is 0 then error "CSV had no rows. Expected header: artist,track"

    set report to my queueTracks(trackSpecs, playlistName, shouldPlay, minScore, strictMode)
    return report
end run

on queueTracks(trackSpecs, playlistName, shouldPlay, minScore, strictMode)
    set missingTracks to {}
    set matchLog to {}
    set addedCount to 0

    tell application "Music"
        activate

        if not (exists user playlist playlistName) then
            make new user playlist with properties {name:playlistName}
        end if
        set queuePlaylist to user playlist playlistName

        try
            delete every track of queuePlaylist
        end try

        repeat with spec in trackSpecs
            set wantedArtist to item 1 of spec
            set wantedTitle to item 2 of spec
            set matchedTrack to missing value
            set matchedVia to "none"
            set bestScore to 0

            -- 1) Song search seeded by title.
            set titleCandidates to {}
            try
                set titleCandidates to search library playlist 1 for wantedTitle only songs
            end try
            set {candTrack, candScore} to my bestMatchFromCandidates(titleCandidates, wantedArtist, wantedTitle, strictMode)
            if candScore > bestScore then
                set bestScore to candScore
                set matchedTrack to candTrack
                set matchedVia to "title"
            end if

            -- 2) Song search seeded by artist.
            set artistCandidates to {}
            try
                set artistCandidates to search library playlist 1 for wantedArtist only songs
            end try
            set {candTrack2, candScore2} to my bestMatchFromCandidates(artistCandidates, wantedArtist, wantedTitle, strictMode)
            if candScore2 > bestScore then
                set bestScore to candScore2
                set matchedTrack to candTrack2
                set matchedVia to "artist"
            end if

            -- 3) Broad fallback seeded by both artist + title.
            set broadCandidates to {}
            try
                set broadCandidates to search library playlist 1 for (wantedArtist & space & wantedTitle) only songs
            end try
            set {candTrack3, candScore3} to my bestMatchFromCandidates(broadCandidates, wantedArtist, wantedTitle, strictMode)
            if candScore3 > bestScore then
                set bestScore to candScore3
                set matchedTrack to candTrack3
                set matchedVia to "broad"
            end if

            if matchedTrack is not missing value and bestScore ≥ minScore then
                duplicate matchedTrack to queuePlaylist
                set addedCount to addedCount + 1
                set end of matchLog to (wantedArtist & " - " & wantedTitle & " => " & (artist of matchedTrack) & " - " & (name of matchedTrack) & " [score " & bestScore & ", via " & matchedVia & "]")
            else
                set end of missingTracks to (wantedArtist & " - " & wantedTitle & " [best " & bestScore & "]")
            end if
        end repeat

        if shouldPlay and addedCount > 0 then
            play (item 1 of (tracks of queuePlaylist))
        end if
    end tell

    return my formatReport(addedCount, missingTracks, matchLog)
end queueTracks

on bestMatchFromCandidates(candidates, wantedArtist, wantedTitle, strictMode)
    set bestTrack to missing value
    set bestScore to 0

    repeat with t in candidates
        try
            tell application "Music"
                set tArtist to artist of t
                set tName to name of t
            end tell
            set s to my scoreTrack(tArtist, tName, wantedArtist, wantedTitle, strictMode)
            if s > bestScore then
                set bestScore to s
                set bestTrack to t
            end if
        end try
    end repeat

    return {bestTrack, bestScore}
end bestMatchFromCandidates

on scoreTrack(tArtist, tName, wantedArtist, wantedTitle, strictMode)
    set s to 0
    set exactTitle to false
    set artistMatched to false
    set titleMatched to false

    if my looseEqual(tArtist, wantedArtist) then
        set artistMatched to true
        set s to s + 90
    else if my looseContains(tArtist, wantedArtist) or my looseContains(wantedArtist, tArtist) then
        set artistMatched to true
        set s to s + 50
    end if

    if my looseEqual(tName, wantedTitle) then
        set exactTitle to true
        set titleMatched to true
        set s to s + 90
    else if my looseContains(tName, wantedTitle) then
        set titleMatched to true
        set s to s + 55
    else if (not strictMode) and my looseContains(wantedTitle, tName) then
        set titleMatched to true
        set s to s + 35
    end if

    set wantedTokens to my tokenize(wantedTitle)
    set gotTokens to my tokenize(tName)
    set tokenOverlap to 0
    repeat with token in wantedTokens
        if gotTokens contains (contents of token) then
            set tokenOverlap to tokenOverlap + 1
            set s to s + 4
        end if
    end repeat

    if strictMode then
        if tokenOverlap ≥ 2 then set titleMatched to true
    else
        if tokenOverlap ≥ 1 then set titleMatched to true
    end if

    -- Penalize very short substring matches (e.g. "Eden" for a long requested title).
    if strictMode and (not exactTitle) and my looseContains(wantedTitle, tName) then
        try
            set wantedLen to count characters of wantedTitle
            set gotLen to count characters of tName
            if wantedLen > 0 and gotLen < (wantedLen * 0.6) then set s to s - 60
        end try
    end if

    -- Do not match unless both artist and title have evidence.
    if not artistMatched then return 0
    if not titleMatched then return 0

    if s < 0 then set s to 0

    return s
end scoreTrack

on looseEqual(a, b)
    if a is missing value or b is missing value then return false
    ignoring case, diacriticals, punctuation, hyphens, white space
        return (a is b)
    end ignoring
end looseEqual

on looseContains(a, b)
    if a is missing value or b is missing value then return false
    ignoring case, diacriticals, punctuation, hyphens, white space
        return (a contains b)
    end ignoring
end looseContains

on tokenize(t)
    if t is missing value then return {}
    set cleaned to my simpleNormalize(t)
    if cleaned is "" then return {}

    set oldTids to AppleScript's text item delimiters
    set AppleScript's text item delimiters to space
    set rawParts to text items of cleaned
    set AppleScript's text item delimiters to oldTids

    set out to {}
    repeat with p in rawParts
        set v to contents of p
        if v is not "" and (count characters of v) > 2 and (my isStopWord(v) is false) then
            if out does not contain v then set end of out to v
        end if
    end repeat
    return out
end tokenize

on isStopWord(tokenText)
    set stopWords to {"the", "and", "for", "with", "feat", "remastered", "mix", "mixed", "version", "edit", "live"}
    return stopWords contains tokenText
end isStopWord

on simpleNormalize(t)
    set x to t as text
    set charsToSpace to {".", ",", ":", ";", "!", "?", "(", ")", "[", "]", "{", "}", "'", "\"", "/", "\\", "&", "-", "_", "–", "—", "+"}
    repeat with ch in charsToSpace
        set x to my replaceText(x, ch, " ")
    end repeat
    set x to my collapseSpaces(x)
    return x
end simpleNormalize

on replaceText(theText, findText, replaceWith)
    set oldTids to AppleScript's text item delimiters
    set AppleScript's text item delimiters to findText
    set parts to text items of theText
    set AppleScript's text item delimiters to replaceWith
    set newText to parts as text
    set AppleScript's text item delimiters to oldTids
    return newText
end replaceText

on collapseSpaces(t)
    set x to t
    repeat while x contains "  "
        set x to my replaceText(x, "  ", " ")
    end repeat
    if x starts with " " then set x to text 2 thru -1 of x
    if x ends with " " then set x to text 1 thru -2 of x
    return x
end collapseSpaces

on loadTracksFromCSV(csvPath)
    set f to POSIX file csvPath
    set rawText to read f as «class utf8»
    set linesList to paragraphs of rawText

    set specs to {}
    set isFirst to true

    repeat with ln in linesList
        set lineText to contents of ln
        if lineText is "" then
            -- skip
        else if isFirst then
            set isFirst to false
        else
            set cols to my splitCSVLine(lineText)
            if (count of cols) ≥ 2 then
                set artistName to my trim(item 1 of cols)
                set trackName to my trim(item 2 of cols)
                if artistName is not "" and trackName is not "" then
                    set end of specs to {artistName, trackName}
                end if
            end if
        end if
    end repeat
    return specs
end loadTracksFromCSV

on splitCSVLine(lineText)
    set cols to {}
    set cur to ""
    set inQuotes to false
    set i to 1
    repeat while i ≤ (count characters of lineText)
        set ch to character i of lineText
        if ch is "\"" then
            if inQuotes and i < (count characters of lineText) and character (i + 1) of lineText is "\"" then
                set cur to cur & "\""
                set i to i + 1
            else
                set inQuotes to not inQuotes
            end if
        else if ch is "," and not inQuotes then
            set end of cols to cur
            set cur to ""
        else
            set cur to cur & ch
        end if
        set i to i + 1
    end repeat
    set end of cols to cur
    return cols
end splitCSVLine

on trim(t)
    set x to t as text
    repeat while x starts with " "
        set x to text 2 thru -1 of x
    end repeat
    repeat while x ends with " "
        set x to text 1 thru -2 of x
    end repeat
    return x
end trim

on formatReport(addedCount, missingTracks, matchLog)
    set report to "Added " & addedCount & " tracks. Missing: " & (count of missingTracks) & "." & return & return
    set report to report & "Matched:" & return
    if (count of matchLog) is 0 then
        set report to report & "(none)" & return
    else
        repeat with m in matchLog
            set report to report & "- " & (contents of m) & return
        end repeat
    end if

    set report to report & return & "Missing:" & return
    if (count of missingTracks) is 0 then
        set report to report & "(none)"
    else
        repeat with m in missingTracks
            set report to report & "- " & (contents of m) & return
        end repeat
    end if
    return report
end formatReport
