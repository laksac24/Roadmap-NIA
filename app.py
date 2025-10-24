from typing import Dict, List, Any
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
import json
import re
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AI Career Roadmap Generator", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@lru_cache()
def get_settings():
    return {"groq_api_key": os.getenv("GROQ_API_KEY")}

class RoadmapRequest(BaseModel):
    target_role: str
    experience_level: str
    total_time: str

class RoadmapResponse(BaseModel):
    roadmap: Dict[str, Any]
    timeline: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    skill_gaps: List[str]
    estimated_duration: str

class FlexibleRoadmapGenerator:
    def __init__(self, groq_api_key: str):
        self.llm = ChatGroq(
            model="openai/gpt-oss-20b",
            temperature=0.1,
            api_key=groq_api_key,
            max_tokens=4096,
            timeout=60
        )
    
    def _parse_time_input(self, time_str: str) -> int:
        time_str = time_str.lower().strip()
        
        match = re.search(r'(\d+\.?\d*)\s*([a-z]*)', time_str)
        if not match:
            numbers = re.findall(r'\d+', time_str)
            if numbers:
                return int(numbers[0])
            return 100
        
        value = float(match.group(1))
        unit = match.group(2) if match.group(2) else 'hours'
        
        conversions = {
            'hour': 1, 'hours': 1, 'hr': 1, 'hrs': 1, 'h': 1,
            'day': 8, 'days': 8, 'd': 8,
            'week': 40, 'weeks': 40, 'wk': 40, 'w': 40,
            'month': 160, 'months': 160, 'mo': 160, 'm': 160,
            'year': 1920, 'years': 1920, 'yr': 1920, 'y': 1920
        }
        
        for key, multiplier in conversions.items():
            if unit.startswith(key) or key.startswith(unit):
                total_hours = int(value * multiplier)
                return min(max(total_hours, 10), 2000)
        
        return int(value)
    
    async def _safe_llm_call(self, prompt: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                return response.content
            except Exception as e:
                if attempt == max_retries - 1:
                    return "{}"
        return "{}"
    
    def _parse_json_safely(self, response_content: str, fallback: dict = None) -> dict:
        try:
            content = response_content.strip()
            
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end != -1:
                    content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                if end != -1:
                    content = content[start:end].strip()
            
            if not content.startswith('{'):
                start_idx = content.find('{')
                if start_idx != -1:
                    end_idx = content.rfind('}')
                    if end_idx != -1:
                        content = content[start_idx:end_idx+1]
            
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return fallback or {}
    
    def _format_time_breakdown(self, total_hours: int, original_input: str) -> Dict[str, Any]:
        return {
            "total_hours": total_hours,
            "original_input": original_input,
            "scheduling_options": {
                "intensive": {
                    "hours_per_day": 4,
                    "total_days": max(1, total_hours // 4),
                    "description": f"Complete in {max(1, total_hours // 4)} days with 4 hours daily"
                },
                "moderate": {
                    "hours_per_day": 2,
                    "total_days": max(1, total_hours // 2),
                    "description": f"Complete in {max(1, total_hours // 2)} days with 2 hours daily"
                },
                "relaxed": {
                    "hours_per_week": 10,
                    "total_weeks": max(1, total_hours // 10),
                    "description": f"Complete in {max(1, total_hours // 10)} weeks with 10 hours weekly"
                },
                "casual": {
                    "hours_per_week": 5,
                    "total_weeks": max(1, total_hours // 5),
                    "description": f"Complete in {max(1, total_hours // 5)} weeks with 5 hours weekly"
                }
            },
            "milestones": [
                {"percentage": 25, "hours": total_hours // 4, "description": "Foundation complete"},
                {"percentage": 50, "hours": total_hours // 2, "description": "Halfway milestone"},
                {"percentage": 75, "hours": int(total_hours * 0.75), "description": "Advanced skills acquired"},
                {"percentage": 100, "hours": total_hours, "description": "Job-ready portfolio"}
            ]
        }
    
    async def generate_complete_roadmap(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        target_role = user_input.get('target_role', '')
        experience_level = user_input.get('experience_level', 'beginner')
        time_input = user_input.get('total_time', '100 hours')
        
        total_hours = self._parse_time_input(time_input)
        buffer_hours = int(total_hours * 0.1)
        learning_hours = total_hours - buffer_hours
        
        prompt = f"""
You are an expert career counselor and tech industry analyst. Generate a comprehensive and realistic career roadmap.

REQUIREMENTS:
- TARGET ROLE: {target_role}
- EXPERIENCE LEVEL: {experience_level}
- TOTAL TIME AVAILABLE: {total_hours} hours (originally "{time_input}")
- LEARNING TIME: {learning_hours} hours (with {buffer_hours} hours buffer)

Create a focused roadmap that:
1. Identifies ALL critical skills needed for {target_role}
2. Starts from the fundamentals appropriate for {experience_level} level
3. Fits within {learning_hours} hours of learning time
4. Includes hands-on projects and milestones
5. Provides a complete learning path from zero to job-ready

Return ONLY valid JSON with this structure:

{{
  "skill_gaps": [
    "HTML & CSS Fundamentals",
    "JavaScript Programming",
    "React.js",
    "Node.js",
    "Database Design",
    "API Development"
  ],
  "estimated_duration": "Flexible timeline based on {total_hours} total hours",
  "roadmap": {{
    "learning_path": [
      {{
        "step": 1,
        "title": "Programming Fundamentals",
        "description": "Start with core programming concepts and web basics",
        "skills_covered": ["HTML", "CSS", "JavaScript Basics", "Programming Logic"],
        "estimated_hours": 40,
        "difficulty": "{experience_level}",
        "prerequisites": [],
        "key_projects": [
          "Personal Website",
          "Interactive Calculator",
          "Simple Portfolio Page"
        ],
        "completion_criteria": [
          "Build 3 static websites",
          "Understand programming basics",
          "Complete 15 coding exercises"
        ]
      }},
      {{
        "step": 2,
        "title": "Advanced JavaScript",
        "description": "Master modern JavaScript for web development",
        "skills_covered": ["JavaScript ES6+", "DOM Manipulation", "Async Programming", "APIs"],
        "estimated_hours": 50,
        "difficulty": "intermediate",
        "prerequisites": ["Programming Fundamentals"],
        "key_projects": [
          "Weather App with API",
          "To-Do List with Local Storage",
          "Interactive Quiz Application"
        ],
        "completion_criteria": [
          "Build dynamic web applications",
          "Handle API integrations",
          "Master asynchronous programming"
        ]
      }}
    ],
    "total_learning_hours": {learning_hours},
    "buffer_hours": {buffer_hours},
    "milestone_projects": [
      {{
        "title": "Personal Portfolio",
        "description": "Professional portfolio showcasing your growing skills",
        "technologies": ["HTML", "CSS", "JavaScript"],
        "estimated_hours": {int(total_hours * 0.15)},
        "completion_at": "40% progress"
      }},
      {{
        "title": "Full-Stack Application",
        "description": "Complete web application demonstrating all learned skills",
        "technologies": ["Frontend Framework", "Backend", "Database", "API"],
        "estimated_hours": {int(total_hours * 0.25)},
        "completion_at": "80% progress"
      }}
    ]
  }},
  "timeline": {{
    "total_hours": {total_hours},
    "learning_hours": {learning_hours},
    "buffer_hours": {buffer_hours},
    "original_input": "{time_input}",
    "scheduling_options": [
      {{
        "pace": "Intensive",
        "hours_per_day": 4,
        "duration": "{max(1, total_hours // 4)} days",
        "description": "Full-time intensive learning"
      }},
      {{
        "pace": "Moderate", 
        "hours_per_day": 2,
        "duration": "{max(1, total_hours // 2)} days",
        "description": "Part-time consistent learning"
      }},
      {{
        "pace": "Relaxed",
        "hours_per_week": 10,
        "duration": "{max(1, total_hours // 10)} weeks",
        "description": "Weekend and evening learning"
      }},
      {{
        "pace": "Casual",
        "hours_per_week": 5,
        "duration": "{max(1, total_hours // 5)} weeks",
        "description": "Slow and steady approach"
      }}
    ],
    "key_milestones": [
      {{
        "milestone": "Foundation Complete",
        "at_hours": {total_hours // 4},
        "at_percentage": 25,
        "deliverable": "Basic programming skills and first projects"
      }},
      {{
        "milestone": "Intermediate Skills",
        "at_hours": {total_hours // 2},
        "at_percentage": 50,
        "deliverable": "Dynamic web applications"
      }},
      {{
        "milestone": "Advanced Skills",
        "at_hours": {int(total_hours * 0.75)},
        "at_percentage": 75,
        "deliverable": "Professional-quality projects"
      }},
      {{
        "milestone": "Job-Ready",
        "at_hours": {total_hours},
        "at_percentage": 100,
        "deliverable": "Complete portfolio and job-ready skills"
      }}
    ]
  }},
  "recommendations": [
    {{
      "category": "free_courses",
      "priority": "high",
      "items": [
        {{
          "title": "Complete {target_role} Bootcamp",
          "provider": "freeCodeCamp",
          "estimated_hours": {int(learning_hours * 0.3)},
          "cost": "Free",
          "url": "https://freecodecamp.org",
          "why_recommended": "Comprehensive curriculum perfect for {experience_level} level learners"
        }},
        {{
          "title": "Interactive Coding Tutorials",
          "provider": "Codecademy",
          "estimated_hours": {int(learning_hours * 0.2)},
          "cost": "Freemium",
          "url": "https://codecademy.com",
          "why_recommended": "Hands-on practice with immediate feedback"
        }}
      ]
    }},
    {{
      "category": "practice_platforms",
      "priority": "medium",
      "items": [
        {{
          "title": "Codewars",
          "description": "Daily coding challenges for problem-solving",
          "time_commitment": "30 minutes daily",
          "cost": "Free",
          "skill_focus": "Algorithm and logic building"
        }},
        {{
          "title": "Frontend Mentor",
          "description": "Real-world frontend challenges",
          "time_commitment": "2-4 hours per challenge",
          "cost": "Freemium",
          "skill_focus": "UI/UX implementation and best practices"
        }}
      ]
    }},
    {{
      "category": "project_ideas",
      "priority": "high",
      "items": [
        {{
          "title": "Personal Blog",
          "difficulty": "{experience_level}",
          "estimated_hours": {int(total_hours * 0.08)},
          "skills_practiced": ["HTML", "CSS", "JavaScript", "Content Management"],
          "portfolio_value": "Shows technical and communication skills"
        }},
        {{
          "title": "E-commerce Product Page",
          "difficulty": "intermediate",
          "estimated_hours": {int(total_hours * 0.12)},
          "skills_practiced": ["Responsive Design", "JavaScript Interactivity", "Form Handling"],
          "portfolio_value": "Demonstrates real-world application skills"
        }},
        {{
          "title": "Task Management Application",
          "difficulty": "advanced",
          "estimated_hours": {int(total_hours * 0.15)},
          "skills_practiced": ["Full-Stack Development", "Database Integration", "User Authentication"],
          "portfolio_value": "Shows complete development capabilities"
        }}
      ]
    }}
  ]
}}

CRITICAL REQUIREMENTS:
- Total learning hours should sum to approximately {learning_hours}
- Include {buffer_hours} hours for review and practice
- All skills should be relevant to {target_role}
- Difficulty progression appropriate for {experience_level} starting level
- Start from complete fundamentals (assume no prior knowledge)
- Include realistic time estimates for each step
- Focus on practical, portfolio-building projects
- Provide a complete path from beginner to job-ready
"""

        response_content = await self._safe_llm_call(prompt)
        
        complete_roadmap = self._parse_json_safely(response_content, {
            "skill_gaps": ["Programming fundamentals", "Web development", "Problem solving", "Version control"],
            "estimated_duration": f"Flexible based on {total_hours} total hours",
            "roadmap": {
                "learning_path": [
                    {
                        "step": 1,
                        "title": "Programming Foundations",
                        "description": f"Learn fundamental programming concepts for {target_role}",
                        "skills_covered": ["Basic programming", "Problem solving", "Logic building"],
                        "estimated_hours": learning_hours // 3,
                        "difficulty": experience_level,
                        "prerequisites": [],
                        "key_projects": ["Hello World program", "Basic calculator"],
                        "completion_criteria": ["Understand basic programming concepts"]
                    },
                    {
                        "step": 2,
                        "title": "Intermediate Skills",
                        "description": f"Build intermediate skills for {target_role}",
                        "skills_covered": ["Advanced programming", "Framework basics"],
                        "estimated_hours": learning_hours // 3,
                        "difficulty": "intermediate",
                        "prerequisites": ["Programming Foundations"],
                        "key_projects": ["Interactive application"],
                        "completion_criteria": ["Build functional applications"]
                    },
                    {
                        "step": 3,
                        "title": "Advanced Concepts",
                        "description": f"Master advanced concepts for {target_role}",
                        "skills_covered": ["Professional development", "Best practices", "Real-world application"],
                        "estimated_hours": learning_hours // 3,
                        "difficulty": "advanced",
                        "prerequisites": ["Intermediate Skills"],
                        "key_projects": ["Portfolio project", "Capstone application"],
                        "completion_criteria": ["Create professional-quality work"]
                    }
                ],
                "total_learning_hours": learning_hours,
                "buffer_hours": buffer_hours,
                "milestone_projects": [
                    {
                        "title": "Learning Portfolio",
                        "description": "Showcase your progress and skills",
                        "technologies": ["Core technologies for the role"],
                        "estimated_hours": int(total_hours * 0.15),
                        "completion_at": "50% progress"
                    },
                    {
                        "title": "Capstone Project",
                        "description": "Comprehensive project demonstrating job readiness",
                        "technologies": ["All learned technologies"],
                        "estimated_hours": int(total_hours * 0.25),
                        "completion_at": "90% progress"
                    }
                ]
            },
            "timeline": self._format_time_breakdown(total_hours, time_input),
            "recommendations": [
                {
                    "category": "free_courses",
                    "priority": "high",
                    "items": [
                        {
                            "title": f"{target_role} Fundamentals Course",
                            "provider": "freeCodeCamp",
                            "estimated_hours": 30,
                            "cost": "Free",
                            "url": "https://freecodecamp.org",
                            "why_recommended": f"Perfect starting point for {experience_level} learners"
                        }
                    ]
                }
            ]
        })
        
        return complete_roadmap

def get_roadmap_generator():
    settings = get_settings()
    if not settings["groq_api_key"]:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY environment variable is required"
        )
    return FlexibleRoadmapGenerator(groq_api_key=settings["groq_api_key"])

@app.post("/generate-roadmap", response_model=RoadmapResponse)
async def generate_roadmap(
    request: RoadmapRequest,
    generator: FlexibleRoadmapGenerator = Depends(get_roadmap_generator)
):
    try:
        user_input = {
            "target_role": request.target_role,
            "experience_level": request.experience_level,
            "total_time": request.total_time
        }
        
        result = await generator.generate_complete_roadmap(user_input)
        return RoadmapResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating roadmap: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": "llama-3.3-70b-versatile"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)