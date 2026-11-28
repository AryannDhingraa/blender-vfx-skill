"""Fixed, local wording for the Studio: what each engine operation is in filmmaking
language, and a short cached explanation of it. Nothing here guesses the creative
purpose of a step; that only comes from what the agent recorded (title, purpose,
component). No AI calls."""

STATE_WORDS = {
    "PASS": "Done, checks passed", "FAIL": "Failed", "UNKNOWN": "Finished, result unclear",
    "NOT_APPLICABLE": "Not needed here", "running": "In progress", "interrupted": "Stopped before finishing",
    "unknown-remote": "Running on the other machine",
}

STAGES = {
    "brief": "Planning the shot", "plate": "Preparing the footage", "analyse": "Studying the footage",
    "track": "Camera tracking", "build": "Building the 3D scene", "light": "Lighting", "preview": "Preview renders",
    "render": "Final render", "comp": "Compositing", "review": "Review", "deliver": "Delivery",
}

# op name -> title, what it does, how it affects the picture, how to do it yourself
OPS = {
    "state init": ("Project initialised",
                   "Created the shot's tracking file, so every later step is recorded and can be checked.",
                   "No change to the picture.",
                   "Nothing to do in Blender: this is the engine's own record keeping."),
    "state set": ("Shot settings updated", "Changed a recorded shot setting or fact.", "No direct change to the picture.",
                  "Not a Blender step."),
    "state done": ("Stage marked complete", "Marked a production stage as finished and moved to the next one.",
                   "No change to the picture.", "Not a Blender step."),
    "state reopen": ("Stage reopened", "Opened a finished stage again so it can be redone.", "No change yet.",
                     "Not a Blender step."),
    "state record": ("Result recorded",
                     "Saved fingerprints of a finished result (and what it was made from) so the engine notices when it goes out of date.",
                     "No change to the picture.", "Not a Blender step."),
    "state invalidate": ("Result marked out of date", "Marked a result and everything built from it as needing to be redone.",
                         "Those parts will be rebuilt before the final.", "Not a Blender step."),
    "state recover": ("Shot record recovered", "Restored the shot's tracking file from its history after damage.",
                      "No change to the picture.", "Not a Blender step."),
    "analyse": ("Checking the footage",
                "Measured how the camera moves (locked off, panning, or moving through space), plus blur and exposure.",
                "Decides how the CG will be locked to your footage. A wrong guess makes CG slide.",
                "In Blender: Movie Clip Editor, play the clip and watch whether near and far objects move at different speeds (parallax)."),
    "verify": ("Checking output quality",
               "Looked for missing, broken, black or flickering frames in a render or video.",
               "No change. It catches problems before you watch the result.",
               "Open the frames or video and step through frame by frame."),
    "run": ("Rendering selected frames",
            "Rendered frames in Blender in the background, with a time limit, then checked every frame it wrote.",
            "Produces new images of the shot with the current scene settings.",
            "In Blender: set the frame range in Output Properties, then Render > Render Animation (or F12 for one frame)."),
    "resume": ("Re-rendering missing or broken frames", "Rendered only the frames that were missing, damaged or out of date.",
               "Fills gaps without redoing good frames.", "In Blender: render just those frame numbers again."),
    "assets download": ("Downloading an approved asset", "Downloaded a model, texture or HDRI you approved and logged its licence.",
                        "Adds a new element you can place in the scene.", "Download it from the site and use File > Import or append it."),
    "tidy": ("Checking folder tidiness", "Listed clutter, temporary files and duplicates. Deletes nothing unless told to.",
             "No change to the picture.", "Look through the project folder in Finder."),
    "preflight": ("Checking production readiness", "Checked that the engine, Blender and tools are installed and working on this machine.",
                  "No change to the picture.", "Not a Blender step."),
    "snapshot": ("Script version recorded", "Saved a copy of a script before it ran, so you can see exactly what changed.",
                 "Depends on what the script does. See the agent's description if one was given.",
                 "Compare the two versions shown below the summary."),
    "note": ("Note from Claude", "A message Claude logged about what it is doing. It is not a verified engine result.",
             "None by itself.", ""),
}


def describe(op):
    """(title, what, effect, manual) for an op name; unknown ops are labelled as technical steps."""
    if op in OPS:
        return OPS[op]
    base = (op or "").split(" ")[0]
    if base in OPS:
        return OPS[base]
    return (f"Technical step: {op}", "An engine step without a plain-language description yet.", "Not recorded.", "")


def glossary():
    return {"ops": {k: {"title": v[0], "what": v[1], "effect": v[2], "manual": v[3]} for k, v in OPS.items()},
            "states": STATE_WORDS, "stages": STAGES}
