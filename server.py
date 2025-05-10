from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
import asyncio
import json
from pathlib import Path
from typing import List, Dict

# Initialize MCP server
mcp = FastMCP("Healthcare MCP Server")

# Define response model
class ToolResponse(BaseModel):
    content: str
    error: bool = False

# Configure dataset paths
DATASET_PATH = Path("dataset")
PATIENTS: List[Dict] = []
MEDICATIONS: Dict = {}
GUIDELINES: List[Dict] = []

# Load mock data
def load_mock_data():
    global PATIENTS, MEDICATIONS, GUIDELINES
    
    try:
        with open(DATASET_PATH / "patients.json") as f:
            PATIENTS = json.load(f)
        
        with open(DATASET_PATH / "medications.json") as f:
            MEDICATIONS = json.load(f)
            
        with open(DATASET_PATH / "guidelines.json") as f:
            GUIDELINES = json.load(f)
            
    except Exception as e:
        print(f"Error loading mock data: {str(e)}")

# Initialize data
load_mock_data()

@mcp.tool()
async def list_patients_tool() -> ToolResponse:
    """List all available patient IDs and names"""
    try:
        patient_list = [{"id": p["id"], "name": p["name"]} for p in PATIENTS]
        return ToolResponse(content=json.dumps({"patients": patient_list}))
    except Exception as e:
        return ToolResponse(content=f"Error listing patients: {str(e)}", error=True)

@mcp.tool()
async def fetch_patient_data_tool(patient_id: str) -> ToolResponse:
    """
    Fetch patient EHR data
    
    Args:
        patient_id: Patient identifier (e.g. PT-1001)
    """
    try:
        if not patient_id:
            return ToolResponse(content="Missing required patient_id", error=True)
        
        patient = next((p for p in PATIENTS if p["id"] == patient_id), None)
        if not patient:
            return ToolResponse(content=f"Patient {patient_id} not found", error=True)
            
        return ToolResponse(content=json.dumps(patient))
    except Exception as e:
        return ToolResponse(content=f"Error fetching patient data: {str(e)}", error=True)

@mcp.tool()
async def check_medication_interactions_tool(medications: List[str]) -> ToolResponse:
    """
    Check medication interactions
    
    Args:
        medications: List of medication names (e.g. ["Aspirin", "Lisinopril"])
    """
    try:
        if not medications or not isinstance(medications, list):
            return ToolResponse(content="Invalid medications list format", error=True)
        
        interactions = []
        for med in medications:
            if med in MEDICATIONS:
                interacting_meds = [m for m in medications 
                                   if m in MEDICATIONS[med].get("interactions", [])]
                if interacting_meds:
                    interactions.append(f"{med} interacts with: {', '.join(interacting_meds)}")
        
        result = interactions if interactions else ["No dangerous interactions found"]
        return ToolResponse(content=json.dumps({"interactions": result}))
    except Exception as e:
        return ToolResponse(content=f"Error checking interactions: {str(e)}", error=True)

@mcp.tool()
async def get_clinical_guidelines_tool(condition: str) -> ToolResponse:
    """
    Retrieve clinical guidelines
    
    Args:
        condition: Medical condition (e.g. hypertension)
    """
    try:
        if not condition:
            return ToolResponse(content="Missing required condition", error=True)
        
        guideline = next(
            (g for g in GUIDELINES 
             if g["condition"].lower() == condition.lower()),
            None
        )
        if not guideline:
            return ToolResponse(content=f"No guidelines found for {condition}", error=True)
            
        return ToolResponse(content=json.dumps(guideline))
    except Exception as e:
        return ToolResponse(content=f"Error fetching guidelines: {str(e)}", error=True)

if __name__ == "__main__":
    mcp.run()