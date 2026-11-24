# Rendering beyond your own machine

| Option | Cost | Good for | Watch out for |
| --- | --- | --- | --- |
| Flamenco on your own machines | Free | Using a second laptop or desktop overnight | Same Blender version everywhere; split by shot, not by alternating frames |
| SheepIt (community render farm) | Free, you earn points by rendering for others | Short animations, non-confidential work | Your files render on strangers' machines; queue times vary |
| Rented cloud GPU (hourly) | Pay per hour | Heavy finals, big simulations, AI models that need NVIDIA | Upload size, matching Blender version and add-ons, shutting the machine down after |
| Commercial Blender render farms | Pay per job | Deadlines | Price estimates before you submit |

Before sending a job anywhere: pack external data into the .blend (File, External Data, Pack Resources) or send the whole project folder, bake every simulation, and render one test frame there first. The agent asks before uploading anything or starting anything that costs money.
