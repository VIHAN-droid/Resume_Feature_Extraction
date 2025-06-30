from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import os
import PyPDF2
import re
import json
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class ResumeParser:
    def __init__(self):
        self.email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        self.phone_pattern = r'(?:\+91[-.\s]?)?(?:\d{10}|\d{3}[-.\s]?\d{3}[-.\s]?\d{4}|\(\d{3}\)[-.\s]?\d{3}[-.\s]?\d{4}|(?:\+\d{1,3}[-.\s]?)?\d{10})'
        self.linkedin_pattern = r'linkedin\.com/in/[\w-]+'
        self.github_pattern = r'github\.com/[\w-]+'
        self.leetcode_pattern = r'leetcode\.com/[\w-]+'
        self.codeforces_pattern = r'codeforces\.com/profile/[\w-]+'
        
    def extract_text_from_pdf(self, pdf_path):
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""
    
    def extract_contact_info(self, text):
        # Clean text and search for patterns
        text_clean = text.replace('\n', ' ').replace('\r', ' ')
        
        # Find emails with better pattern
        emails = re.findall(self.email_pattern, text_clean, re.IGNORECASE)
        
        # Find phones with multiple patterns
        phones = re.findall(self.phone_pattern, text_clean)
        
        # Clean phone numbers
        if phones:
            phone = phones[0]
            # Remove extra characters and format
            phone = re.sub(r'[^\d+]', '', phone)
            if len(phone) >= 10:
                phones = [phone]
        
        return {
            'email': emails[0] if emails else None,
            'phone': phones[0] if phones else None
        }
    
    def extract_name(self, text):
        lines = text.strip().split('\n')
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line and len(line.split()) <= 4 and not any(char.isdigit() for char in line):
                return line
        
        return None
    
    def extract_social_handles(self, text):
        linkedin = re.findall(self.linkedin_pattern, text, re.IGNORECASE)
        github = re.findall(self.github_pattern, text, re.IGNORECASE)
        leetcode = re.findall(self.leetcode_pattern, text, re.IGNORECASE)
        codeforces = re.findall(self.codeforces_pattern, text, re.IGNORECASE)
        
        return {
            'linkedin': linkedin[0] if linkedin else None,
            'github': github[0] if github else None,
            'leetcode': leetcode[0] if leetcode else None,
            'codeforces': codeforces[0] if codeforces else None
        }
    
    def extract_education(self, text):
        education_keywords = ['university', 'college', 'institute', 'school', 'bachelor', 'master', 'phd', 'degree']
        cgpa_pattern = r'cgpa[:\s]*(\d+\.?\d*)[/\s]*(\d+\.?\d*)?'
        gpa_pattern = r'gpa[:\s]*(\d+\.?\d*)[/\s]*(\d+\.?\d*)?'
        
        lines = text.lower().split('\n')
        education_info = []
        
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in education_keywords):
                # Look for CGPA/GPA in current and next few lines
                cgpa_match = re.search(cgpa_pattern, ' '.join(lines[i:i+3]), re.IGNORECASE)
                gpa_match = re.search(gpa_pattern, ' '.join(lines[i:i+3]), re.IGNORECASE)
                
                education_info.append({
                    'institution': line.strip(),
                    'cgpa': cgpa_match.group(1) if cgpa_match else (gpa_match.group(1) if gpa_match else None)
                })
        
        return education_info
    
    def extract_skills(self, text):
        skills_keywords = ['skills', 'technical skills', 'programming languages', 'technologies']
        lines = text.split('\n')
        skills = []
        
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in skills_keywords):
                # Extract next few lines as skills
                for j in range(i+1, min(i+5, len(lines))):
                    skill_line = lines[j].strip()
                    if skill_line and not any(stop_word in skill_line.lower() for stop_word in ['experience', 'education', 'project']):
                        skills.extend([skill.strip() for skill in skill_line.split(',') if skill.strip()])
                break
        
        return skills
    
    def extract_projects(self, text):
        project_keywords = ['projects', 'project work', 'academic projects']
        lines = text.split('\n')
        projects = []
        
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in project_keywords):
                current_project = ""
                for j in range(i+1, min(i+10, len(lines))):
                    project_line = lines[j].strip()
                    if project_line and not any(stop_word in project_line.lower() for stop_word in ['experience', 'education', 'skill']):
                        if project_line.startswith('•') or project_line.startswith('-') or project_line.startswith('*'):
                            if current_project:
                                projects.append(current_project.strip())
                            current_project = project_line
                        else:
                            current_project += " " + project_line
                    elif current_project:
                        projects.append(current_project.strip())
                        current_project = ""
                
                if current_project:
                    projects.append(current_project.strip())
                break
        
        return projects
    
    def extract_experience(self, text):
        exp_keywords = ['experience', 'work experience', 'employment', 'internship']
        lines = text.split('\n')
        experience = []
        
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in exp_keywords):
                current_exp = ""
                for j in range(i+1, min(i+8, len(lines))):
                    exp_line = lines[j].strip()
                    if exp_line and not any(stop_word in exp_line.lower() for stop_word in ['education', 'skill', 'project']):
                        if exp_line.startswith('•') or exp_line.startswith('-') or exp_line.startswith('*'):
                            if current_exp:
                                experience.append(current_exp.strip())
                            current_exp = exp_line
                        else:
                            current_exp += " " + exp_line
                    elif current_exp:
                        experience.append(current_exp.strip())
                        current_exp = ""
                
                if current_exp:
                    experience.append(current_exp.strip())
                break
        
        return experience
    
    def parse_resume(self, pdf_path):
        """Main function to parse resume and extract all information"""
        text = self.extract_text_from_pdf(pdf_path)
        
        if not text:
            return {"error": "Could not extract text from PDF"}
        
        result = {
            'name': self.extract_name(text),
            'contact': self.extract_contact_info(text),
            'social_handles': self.extract_social_handles(text),
            'education': self.extract_education(text),
            'skills': self.extract_skills(text),
            'projects': self.extract_projects(text),
            'experience': self.extract_experience(text),
            'raw_text': text[:500] + "..." if len(text) > 500 else text  # First 500 chars for debugging
        }
        
        return result

# Initialize parser
parser = ResumeParser()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.lower().endswith('.pdf'):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(filepath)
            
            # Parse the resume
            result = parser.parse_resume(filepath)
            
            # Clean up uploaded file
            os.remove(filepath)
            
            return jsonify(result)
            
        except Exception as e:
            # Clean up file if it exists
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': f'Error processing file: {str(e)}'}), 500
    
    return jsonify({'error': 'Only PDF files are supported'}), 400

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=8001, threaded=True)