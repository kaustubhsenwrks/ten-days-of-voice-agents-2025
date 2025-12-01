import logging
import json
import random
import os
import sys
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import uuid

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    metrics,
    tokenize,
    function_tool,
    cli,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Windows-specific imports and fixes
if os.name == "nt":
    import signal
    if not hasattr(signal, "SIGKILL"):
        signal.SIGKILL = signal.SIGTERM
    # Set event loop policy for Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = logging.getLogger("improv-battle-agent")

# Load environment variables
env_path = Path(".env.local")
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()  # Fallback to default .env

class ImprovBattleAgent(Agent):
    """
    Single–player Improv Battle host.

    State is stored per Agent instance in self.improv_state.
    The LLM manipulates state via the tools below.
    """

    def __init__(self) -> None:
        super().__init__(
            instructions="""
You are the high-energy host of a TV improv show called **"Improv Battle"**.

GENERAL VIBE
- You are witty, playful, and confident.
- You explain the rules clearly, keep things moving, and stay respectful.
- You can tease and critique the player lightly, but never be mean, abusive, or insulting.

GAME STRUCTURE (SINGLE PLAYER)
- There is exactly ONE human player in the room.
- The backend keeps a game state object with:
    - player_name
    - current_round
    - max_rounds (usually 3)
    - rounds: list of past scenes with scenario + reaction
    - phase: "intro" | "awaiting_improv" | "reacting" | "done"
- You interact with that state ONLY via the tools:
    - get_game_state
    - set_player_name
    - start_new_round
    - complete_round
    - end_game

YOUR FLOW

1) INTRO
- On first contact:
    - Call get_game_state.
    - If player_name is missing and the client did not clearly specify it, politely ask their name.
      Once you know it, call set_player_name.
    - Explain the show in 2–3 sentences:
        - There will be several short improv rounds (usually 3).
        - Each round you give a scenario.
        - The player performs in character.
        - When they say "end scene", "okay I'm done", or pause after a natural ending, you react.
    - Then call start_new_round to get the first scenario and present it.

2) EACH ROUND
- A round has two phases controlled by tools and your behaviour:

   A) SCENARIO & IMPROV
   - Call get_game_state and check phase.
   - If phase is "awaiting_improv", you should present the scenario clearly:
        - Who the player is.
        - Where they are.
        - What the tension or problem is.
     Example style:
        "Alright Round 2! You are a time-travelling tour guide trying to explain modern smartphones
         to someone from the 1800s. Whenever you're ready, jump into character and start your scene!"
   - Then you WAIT for the player to improvise in character.
   - DO NOT immediately start another scenario; let them speak for a bit.
   - When you believe the player is done (they say "end scene", "okay that's it", "I'm done", or it
     sounds like a natural end), move to REACTION.

   B) REACTION
   - First, think about your tone:
        - Roughly 1/3 of the time: mostly supportive & enthusiastic.
        - 1/3 of the time: mixed — some praise, some light critique.
        - 1/3 of the time: more critical but still kind and constructive.
   - Comment on:
        - What was funny, surprising, or interesting.
        - Where they could lean more into the character, emotion, or absurdity.
   - Keep reactions to ~3–6 sentences so the game keeps moving.
   - After you speak your reaction:
        - Call complete_round with:
            - reaction_summary: a short 1–2 sentence summary of how the scene went.
            - tone: "supportive" | "mixed" | "critical".
        - Then:
            - If current_round < max_rounds: call start_new_round and introduce the next scenario.
            - If current_round == max_rounds: move to CLOSING.

3) CLOSING SUMMARY
- When the game reaches max_rounds OR the phase becomes "done":
    - Give a short summary of the player's *overall improv style* based on the stored rounds:
        - Are they more character-focused, absurd, story-driven, emotional, deadpan, etc.?
    - Mention at least one specific moment or scene detail that stood out.
    - Thank them for playing Improv Battle and tell them they can start again if they want.

EARLY EXIT
- If the user clearly says something like:
    - "stop game", "end show", "I want to stop now", "let's finish here"
  then:
    - Call end_game(reason="user_requested_stop").
    - Give a short graceful outro and do not start new rounds.

SCENARIOS
- You DO NOT need a tool to generate scenarios; you invent them.
- Scenarios must ALWAYS:
    - Clearly say who the player is.
    - Give a situation and a tension or problem.
    - Encourage character and emotion, not trivia.
- Examples (DO NOT repeat verbatim every time, just use similar style):
    - "You are a time-travelling tour guide explaining modern smartphones to someone from the 1800s."
    - "You are a restaurant waiter who must calmly tell a customer that their order has escaped the kitchen."
    - "You are a customer trying to return an obviously cursed object to a very skeptical shop owner."
    - "You are a barista who has to tell a customer that their latte is actually a portal to another dimension."

TONE & SAFETY
- Never insult, mock, or bully the player.
- Light teasing is okay, for example:
    - "That ending was wild, I did NOT see that coming."
    - "You abandoned your character a bit at the end, but the start was strong."
- Keep language PG-13: no explicit sexual content, hate speech, or self-harm encouragement.

REMINDERS
- Use the tools to keep backend state in sync.
- Do NOT expose tool names directly to the user; just talk like a normal host.
- Stay in character as the Improv Battle host at all times.
"""
        )

        # Simple state per session
        self.improv_state: Dict[str, Any] = {
            "player_name": None,
            "current_round": 0,
            "max_rounds": 3,
            "rounds": [],  # list[{"round_number", "scenario", "reaction_summary", "tone"}]
            "phase": "intro",  # "intro" | "awaiting_improv" | "reacting" | "done"
            "current_scenario": None,
        }

    # --------- TOOLS EXPOSING BACKEND STATE ---------

    @function_tool
    async def get_game_state(self, context: RunContext) -> Dict[str, Any]:
        """Get the current improv game state (read-only for the model)."""
        return self.improv_state

    @function_tool
    async def set_player_name(self, context: RunContext, player_name: str) -> Dict[str, Any]:
        """Set or update the player's display name."""
        self.improv_state["player_name"] = player_name.strip() or "Player"
        return self.improv_state

    @function_tool
    async def start_new_round(self, context: RunContext) -> Dict[str, Any]:
        """
        Start the next improv round.

        Increments the round counter, sets phase to 'awaiting_improv', and
        generates a scenario string for this round.
        """
        if self.improv_state["phase"] == "done":
            return {
                "status": "finished",
                "message": "Game is already finished.",
                "state": self.improv_state,
            }

        # If already at or beyond max rounds, mark done
        if self.improv_state["current_round"] >= self.improv_state["max_rounds"]:
            self.improv_state["phase"] = "done"
            return {
                "status": "finished",
                "message": "Reached maximum rounds.",
                "state": self.improv_state,
            }

        self.improv_state["current_round"] += 1
        self.improv_state["phase"] = "awaiting_improv"

        round_no = self.improv_state["current_round"]
        name = self.improv_state["player_name"] or "Player"

        # A small pool of scenario templates; we will sample from them.
        base_scenarios = [
            "You are a time-travelling tour guide trying to explain modern smartphones to someone from the 1800s.",
            "You are a restaurant waiter who must calmly tell a customer that their order has escaped the kitchen.",
            "You are a customer trying to return an obviously cursed object to a very skeptical shop owner.",
            "You are a barista who has to tell a customer that their latte is actually a portal to another dimension.",
            "You are a superhero whose only power is giving unbelievably specific but useless life advice.",
            "You are a tech support agent explaining to a medieval knight why they cannot swing their sword at the Wi-Fi router.",
            "You are a weather reporter who can secretly control the weather but must pretend everything is normal.",
        ]

        scenario = random.choice(base_scenarios)
        # Add player name and round context to help the host phrase it nicely.
        decorated_scenario = f"Round {round_no} for {name}: {scenario}"

        self.improv_state["current_scenario"] = decorated_scenario

        return {
            "status": "ok",
            "scenario": decorated_scenario,
            "state": self.improv_state,
        }

    @function_tool
    async def complete_round(
        self,
        context: RunContext,
        reaction_summary: str,
        tone: str,
    ) -> Dict[str, Any]:
        """
        Mark the current round as completed and store host reaction info.

        The LLM should call this AFTER giving its spoken reaction to the scene.
        - reaction_summary: 1–2 sentence text summary of how the scene went.
        - tone: one of "supportive", "mixed", or "critical".
        """
        current_round = self.improv_state["current_round"]
        scenario = self.improv_state.get("current_scenario")

        if not scenario or current_round == 0:
            return {
                "status": "error",
                "message": "No active round to complete.",
                "state": self.improv_state,
            }

        self.improv_state["rounds"].append(
            {
                "round_number": current_round,
                "scenario": scenario,
                "reaction_summary": reaction_summary.strip(),
                "tone": tone.strip().lower(),
            }
        )

        # After reaction, either we will start a new round or finish the game.
        # Phase will be updated by start_new_round or end_game.
        self.improv_state["phase"] = "reacting"
        self.improv_state["current_scenario"] = None

        # If this was the last round, we mark as done here so the host knows to summarize.
        if current_round >= self.improv_state["max_rounds"]:
            self.improv_state["phase"] = "done"

        return {
            "status": "ok",
            "state": self.improv_state,
        }

    @function_tool
    async def end_game(self, context: RunContext, reason: str = "user_requested_stop") -> Dict[str, Any]:
        """
        End the game early, e.g. when the user asks to stop.
        """
        self.improv_state["phase"] = "done"
        return {
            "status": "ended",
            "reason": reason,
            "state": self.improv_state,
        }


def prewarm(proc: JobProcess):
    """Pre-warm the VAD model."""
    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("VAD model pre-warmed successfully")
    except Exception as e:
        logger.error(f"Error in prewarm: {e}")
        # Don't raise, continue without VAD if necessary


async def entrypoint(ctx: JobContext):
    """Entry point for the Improv Battle agent."""
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    logger.info(f"Starting Improv Battle agent in room: {ctx.room.name}")

    try:
        agent = ImprovBattleAgent()

        # Get VAD from prewarm or create new
        vad_instance = ctx.proc.userdata.get("vad")
        if not vad_instance:
            logger.warning("VAD not pre-warmed, loading now...")
            vad_instance = silero.VAD.load()

        session = AgentSession(
            stt=deepgram.STT(model="nova-3"),
            llm=google.LLM(model="gemini-2.5-flash"),
            tts=murf.TTS(
                voice="en-US-matthew",  # or any Murf Falcon voice you like
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            ),
            turn_detection=MultilingualModel(),
            vad=vad_instance,
            preemptive_generation=True,
        )

        usage_collector = metrics.UsageCollector()

        @session.on("metrics_collected")
        def _on_metrics_collected(ev: MetricsCollectedEvent):
            metrics.log_metrics(ev.metrics)
            usage_collector.collect(ev.metrics)

        async def log_usage():
            try:
                summary = usage_collector.get_summary()
                logger.info(f"Usage: {summary}")
            except Exception as e:
                logger.error(f"Error logging usage: {e}")

        ctx.add_shutdown_callback(log_usage)

        await session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )

        await ctx.connect()

    except Exception as e:
        logger.error(f"Error in entrypoint: {e}")
        raise


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(name)-12s %(message)s',
        datefmt='%H:%M:%S'
    )
    
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="improv-battle-agent"   # ⭐ MUST MATCH FRONTEND
        )
    )