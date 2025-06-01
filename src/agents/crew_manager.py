"""Crew Manager for Deutsche Telekom Simulator
------------------------------------------
This module provides a more structured approach to using CrewAI in the Deutsche Telekom Simulator.
It handles the creation and management of agents and tasks, leveraging CrewAI's capabilities
while ensuring compatibility with LM Studio.
"""

import os
import time
import threading
import concurrent.futures
from typing import Dict, List, Tuple, Optional
from crewai import Agent, Task, Crew, Process
from src.core.llm_adapter import get_llm
from src.data.prompts import (
    TELEKOM_TASK_PROMPT,
    CUSTOMER_TASK_PROMPT,
    TERMINATOR_TASK_PROMPT,
    TERMINATOR_USER_TASK_PROMPT,
    TERMINATOR_LAST_EXCHANGE_PROMPT,
    CONFIRMATION_TASK_PROMPT,
    CUSTOMER_INTRO_PROMPT
)

class TelekomCrewManager:
    """
    Manager for CrewAI agents and tasks in the Deutsche Telekom Simulator.
    
    This class handles the creation and management of agents and tasks,
    providing a more structured approach to using CrewAI while ensuring
    compatibility with LM Studio.
    """
    
    def __init__(self):
        """Initialize the CrewAI manager with agents."""
        # Initialize the LLM
        self.llm = get_llm()
        
        # Create the agents
        self.customer_agent = self._create_customer_agent()
        self.telekom_agent = self._create_telekom_agent()
        self.terminator_agent = self._create_terminator_agent()
    
    def _create_customer_agent(self) -> Agent:
        """Create the customer agent."""
        return Agent(
            role='Deutsche Telekom Customer',
            goal='Express needs and preferences for a mobile plan, and select a plan if it meets your needs',
            backstory='You are a customer looking for a Deutsche Telekom mobile plan that fits your needs.',
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
    
    def _create_telekom_agent(self) -> Agent:
        """Create the Telekom agent."""
        return Agent(
            role='Deutsche Telekom Agent',
            goal='Help customers find the best mobile plan for their needs',
            backstory='You are a helpful Deutsche Telekom agent who knows all about the available mobile plans.',
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
    
    def _create_terminator_agent(self) -> Agent:
        """Create the terminator agent that determines if a plan has been selected."""
        return Agent(
            role='Terminator Agent',
            goal='Determine if the customer has explicitly selected a plan',
            backstory=(
                'You analyze customer messages to determine if they have explicitly selected a plan. '
                'You are extremely strict about what counts as a selection. '
                'You immediately reject any message containing question marks. '
                'You require clear purchase language and a specific plan name.'
            ),
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
    
    def get_customer_intro(self, persona_name: str, persona_needs: str) -> Task:
        """Get a task for the customer's first message."""
        return Task(
            description=CUSTOMER_INTRO_PROMPT.format(
                persona_name=persona_name,
                persona_needs=persona_needs
            ),
            agent=self.customer_agent,
            expected_output="A natural first message from the customer to the Telekom agent."
        )
    
    def get_customer_response_task(
        self, 
        persona_name: str, 
        persona_needs: str, 
        conversation_history: str,
        bot_message: str,
        prev_customer_msgs: List[str]
    ) -> Task:
        """Get a task for the customer's response."""
        return Task(
            description=CUSTOMER_TASK_PROMPT.format(
                persona_name=persona_name,
                persona_needs=persona_needs,
                conversation_history=conversation_history,
                bot_message=bot_message,
                prev_customer_msgs="\n".join(prev_customer_msgs)
            ),
            agent=self.customer_agent,
            expected_output="A natural response from the customer to the Telekom agent."
        )
    
    def get_telekom_response_task(
        self, 
        conversation_history: str, 
        tariffs: str,
        persona: str
    ) -> Task:
        """Get a task for the Telekom agent's response."""
        return Task(
            description=TELEKOM_TASK_PROMPT.format(
                conversation_history=conversation_history,
                tariffs=tariffs,
                persona=persona
            ),
            agent=self.telekom_agent,
            expected_output="A helpful response from the Telekom agent to the customer."
        )
    
    def get_terminator_task(self, user_message: str) -> Task:
        """Get a task to determine if the customer has selected a plan.
        
        Args:
            user_message: The customer's message to analyze
            
        Returns:
            Task: A task for the terminator agent to analyze the message
        """
        # Log the message being analyzed by the terminator agent
        print(f"[TERMINATOR] Analyzing message: '{user_message[:50]}{'...' if len(user_message) > 50 else ''}'")
        
        # Check for question marks as an early indicator
        if '?' in user_message:
            print(f"[TERMINATOR] Quick check: Message contains question mark, will likely reject")
            
        return Task(
            description=TERMINATOR_USER_TASK_PROMPT.format(user_message=user_message),
            agent=self.terminator_agent,
            expected_output="YES: [plan name] or NO with reason"
        )
    
    def get_confirmation_task(self, plan_name: str) -> Task:
        """Get a task for the confirmation message."""
        return Task(
            description=CONFIRMATION_TASK_PROMPT.format(plan_name=plan_name),
            agent=self.telekom_agent,
            expected_output="A confirmation message from the Telekom agent."
        )
    
    def create_crew(self) -> Crew:
        """Create a CrewAI crew with all agents."""
        return Crew(
            agents=[self.customer_agent, self.telekom_agent, self.terminator_agent],
            tasks=[],
            verbose=True,
            process=Process.sequential
        )
    
    def _determine_task_type(self, task: Task) -> str:
        """Determine the type of task based on the description.
        
        Args:
            task: The task to analyze
            
        Returns:
            str: A short description of the task type
        """
        description = task.description.lower() if hasattr(task, 'description') else ''
        
        if "terminator" in task.agent.role.lower():
            return "plan selection analysis"
        elif "introduction" in description or "first message" in description:
            return "customer introduction"
        elif "respond to the customer" in description:
            return "customer response"
        elif "generate a welcome message" in description:
            return "confirmation"
        else:
            return "task"
            
    def _execute_task_with_llm(self, task: Task) -> str:
        """Execute a task using the LLM and return the result.
        
        This method is used by the ThreadPoolExecutor to run tasks in a separate thread.
        """
        # Use the task's execute method to get the result
        return task.execute()
    
    def execute_single_task(self, task: Task, timeout: int = 120, max_retries: int = 1) -> str:
        """Execute a single task with timeout monitoring."""
        # Get agent role for better logging
        agent_role = task.agent.role if hasattr(task.agent, 'role') else 'Agent'
        task_type = self._determine_task_type(task)
        
        print(f"[TASK] {agent_role} starting {task_type} task")
        
        for attempt in range(max_retries + 1):
            try:
                # Use a monitoring mechanism to log long-running tasks
                result = None
                start_time = time.time()
                
                # Start the task execution in a separate thread
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._execute_task_with_llm, task)
                    
                    # Monitor the execution and provide updates
                    while not future.done():
                        elapsed = time.time() - start_time
                        
                        # Check if we've exceeded the timeout
                        if elapsed > timeout:
                            raise TimeoutError(f"Task execution timed out after {timeout} seconds")
                            
                        # Provide periodic updates if taking longer than expected
                        if elapsed > 30 and elapsed % 15 < 0.1:  # Every ~15 seconds after the first 30
                            print(f"[TASK] {agent_role} {task_type} task running for {elapsed:.1f} seconds")
                            
                        time.sleep(0.1)  # Small sleep to prevent CPU spinning
                    
                    # Get the result (this will re-raise any exception from the thread)
                    result = future.result()
                    
                elapsed = time.time() - start_time
                print(f"[TASK] {agent_role} {task_type} task completed in {elapsed:.1f} seconds")
                
                # For terminator agent, log the decision with more detail
                if agent_role == 'Terminator Agent':
                    if result.upper().startswith("YES:"):
                        plan_name = result[4:].strip()
                        print(f"[TERMINATOR] DECISION: Selected plan '{plan_name}'")
                    else:
                        reason = result[3:].strip() if result.upper().startswith("NO:") else ""
                        print(f"[TERMINATOR] DECISION: No plan selected{f' - {reason}' if reason else ''}")

                
                return result
                
            except Exception as e:
                if attempt < max_retries:
                    print(f"[ERROR] {agent_role} {task_type} task failed, retrying... ({attempt+1}/{max_retries})")
                else:
                    print(f"[ERROR] {agent_role} {task_type} task failed after {max_retries} retries: {str(e)}")
                    raise  # Re-raise the exception
