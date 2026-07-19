# Aegis Competition Demo

## Before You Start

- Start Aegis with `docker compose up --build`.
- Open `http://localhost:8000`.
- For the reliable judge scenario, no external APIs or bridge lookup are required. The scenario fixtures are in `demo/`; the dashboard's **Load flood-threat scenario** control loads the same simulated input profile with live data disabled.

## Two-Minute Story

### 0:00-0:15 - The problem

"Emergency teams often must make time-sensitive decisions using fragmented information. Aegis brings explainable bridge, weather, flood, alert, and field evidence into one operational picture, while keeping every action under human authority."

### 0:15-0:30 - Load the scenario

Click **Load flood-threat scenario** for the simulated story, or use **Find official bridges** and select a record for a live-data walkthrough.

"This records a severe forecast, visible scour, an aging bridge, and a disrupted emergency route. The scenario is visibly marked as simulated so no one mistakes it for a live emergency."

### 0:30-0:50 - Run the assessment

Click **Run risk assessment**.

"Aegis combines the reported infrastructure condition with the simulated environmental and access inputs. The score is deterministic and explainable; AI does not decide the score. In a live operational use case, the same workflow can add public weather, river-gauge, map, bridge, and routing context."

### 0:50-1:20 - Show the map

For the offline judge scenario, point to the risk explanation, action plan, specialist findings, and report rather than relying on map layers. For a live-data walkthrough, point to the city-level assessment marker, nearby mapped bridges, the blue flood-risk screening overlay, and the purple illustrative route.

"The blue overlay is a flood-risk screening area, not an official evacuation zone. The purple line is a routing illustration, not a verified closure detour. That distinction matters: Aegis supports a responder's judgment rather than issuing authority it does not have."

### 1:20-1:45 - Show the agents and report

Scroll to the specialist agent findings and the public alert draft.

"Weather, Flood, Infrastructure, and Routing specialists contribute shared evidence. The Emergency Planning and Coordinator agents turn that evidence into a reviewable, deterministic assessment. Groq can improve the writing of the report, but a human must approve every alert, closure, or dispatch."

### 1:45-2:00 - Close

"Aegis turns fragmented warning signals into an early, explainable operational picture. The next production milestone is connecting authenticated inspection records and calibrated flood models with emergency-agency partners."
