#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# By EWONDJO JOSEPH WILFRIED 21T2332
"""
Générateur d'emploi du temps pour le département d'informatique
Utilise OR-Tools pour résoudre le problème de programmation par contraintes
"""

import json
import os
from ortools.sat.python import cp_model
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet


class TimeTableGenerator:
    """Classe principale pour la génération d'emploi du temps"""
    
    def __init__(self, rooms_file='data/rooms.json', subjects_file='data/subjects.json'):
        """Initialise le générateur avec les chemins des fichiers de données"""
        self.rooms_file = rooms_file
        self.subjects_file = subjects_file
        self.rooms_data = {}
        self.subjects_data = []
        self.processed_data = {}
        self.timetable = {}
        
        # Jours et périodes
        self.days = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi']
        self.periods = [
            ('07:00-09:55', 1),  # Période 1 avec poids 1 (priorité la plus élevée)
            ('10:05-12:55', 2),  # Période 2 avec poids 2
            ('13:05-15:55', 3),  # Période 3 avec poids 3
            ('16:05-18:55', 4),  # Période 4 avec poids 4
            ('19:05-21:55', 5)   # Période 5 avec poids 5 (priorité la plus basse)
        ]
    
    def load_data(self):
        """Charge les données depuis les fichiers JSON"""
        try:
            # Vérifier que les fichiers existent
            if not os.path.exists(self.rooms_file):
                raise FileNotFoundError(f"Le fichier {self.rooms_file} n'existe pas")
            if not os.path.exists(self.subjects_file):
                raise FileNotFoundError(f"Le fichier {self.subjects_file} n'existe pas")
            
            # Charger les données des salles
            with open(self.rooms_file, 'r', encoding='utf-8') as f:
                self.rooms_data = json.load(f)
            
            # Charger les données des matières
            with open(self.subjects_file, 'r', encoding='utf-8') as f:
                subjects_json = json.load(f)
                
                # Aplatir la structure des matières
                all_subjects = []
                for niveau_id, niveau in subjects_json.get('niveau', {}).items():
                    for semestre_id, semestre in niveau.items():
                        for subject in semestre.get('subjects', []):
                            # Ajouter le niveau et le semestre aux informations de la matière
                            subject['niveau'] = niveau_id
                            subject['semestre'] = semestre_id
                            all_subjects.append(subject)
                
                self.subjects_data = all_subjects
            
            print(f"Données chargées avec succès: {len(self.rooms_data.get('Informatique', []))} salles et {len(self.subjects_data)} matières")
            return True
            
        except Exception as e:
            print(f"Erreur lors du chargement des données: {e}")
            return False
    
    def preprocess_data(self):
        """Prétraite les données pour le modèle"""
        try:
            # Extraction des salles
            rooms = [room['num'] for room in self.rooms_data.get('Informatique', []) if 'num' in room]
            
            # Extraction des classes, cours et enseignants
            classes = set()
            courses = {}
            teachers = set()
            curriculum = {}
            
            # Organiser par niveau/semestre
            for subject in self.subjects_data:
                code = subject.get('code')
                if not code:
                    continue
                    
                # Extraire niveau et semestre du code ou des métadonnées
                level = subject.get('niveau', code[3] if len(code) > 3 else '1')
                semester = subject.get('semestre', 's1' if int(code[-1]) <= 5 else 's2')
                class_name = f"L{level}_{semester}"
                
                classes.add(class_name)
                if class_name not in curriculum:
                    curriculum[class_name] = []
                
                curriculum[class_name].append(code)
                
                # Gestion des enseignants
                lecturers = subject.get('Course Lecturer', [])
                assistants = subject.get('Assitant lecturer', [])
                
                # Convertir en liste si ce n'est pas déjà le cas
                if isinstance(lecturers, str):
                    lecturers = [lecturers]
                if isinstance(assistants, str):
                    assistants = [assistants]
                
                # Filtrer les valeurs vides
                valid_lecturers = [l.strip() for l in lecturers if l and isinstance(l, str) and l.strip()]
                valid_assistants = [a.strip() for a in assistants if a and isinstance(a, str) and a.strip()]
                
                courses[code] = {
                    'name': subject.get('name', 'Sans nom'),
                    'lecturers': valid_lecturers,
                    'assistants': valid_assistants,
                    'credit': subject.get('credit', 0)
                }
                
                teachers.update(valid_lecturers)
                teachers.update(valid_assistants)
            
            # Stocker les données prétraitées
            self.processed_data = {
                'classes': sorted(list(classes)),
                'courses': courses,
                'teachers': sorted(list(teachers)),
                'rooms': rooms,
                'curriculum': curriculum,
                'days': self.days,
                'periods': self.periods
            }
            
            print("\nDonnées prétraitées avec succès:")
            print(f"- Classes: {len(self.processed_data['classes'])}")
            print(f"- Cours: {len(self.processed_data['courses'])}")
            print(f"- Enseignants: {len(self.processed_data['teachers'])}")
            print(f"- Salles: {len(self.processed_data['rooms'])}")
            
            return True
            
        except Exception as e:
            print(f"Erreur lors du prétraitement des données: {e}")
            return False
    
    def create_model(self):
        """Crée et résout le modèle d'optimisation"""
        if not self.processed_data or not self.processed_data.get('classes'):
            print("Données insuffisantes pour créer le modèle.")
            return False
        
        model = cp_model.CpModel()
        assignments = {}
        
        try:
            print("\nCréation du modèle d'optimisation...")
            
            # Variables de décision
            # Pour chaque combinaison (classe, cours, enseignant, salle, jour, période),
            # on crée une variable booléenne qui vaut 1 si le cours est programmé à ce moment, 0 sinon
            for class_name in self.processed_data['classes']:
                for course_code in self.processed_data['curriculum'].get(class_name, []):
                    course_info = self.processed_data['courses'].get(course_code, {})
                    teachers_for_course = course_info.get('lecturers', []) + course_info.get('assistants', [])
                    
                    # S'il n'y a pas d'enseignant défini, on utilise un enseignant "Non assigné"
                    if not teachers_for_course:
                        teachers_for_course = ["Non assigné"]
                    
                    for teacher in teachers_for_course:
                        if not isinstance(teacher, str) or not teacher.strip():
                            continue
                        
                        for room in self.processed_data['rooms']:
                            for day in self.processed_data['days']:
                                for period, _ in self.processed_data['periods']:
                                    key = (class_name, course_code, teacher, room, day, period)
                                    assignments[key] = model.NewBoolVar(
                                        f'{class_name}_{course_code}_{teacher}_{room}_{day}_{period}'
                                    )
            
            # Contraintes
            
            # 1. Chaque cours doit être programmé exactement une fois par semaine
            for class_name in self.processed_data['classes']:
                for course_code in self.processed_data['curriculum'].get(class_name, []):
                    course_vars = [
                        assignments[key] for key in assignments
                        if key[0] == class_name and key[1] == course_code
                    ]
                    if course_vars:
                        model.AddExactlyOne(course_vars)
            
            # 2. Pas de conflit de classe (une classe ne peut pas avoir deux cours en même temps)
            for class_name in self.processed_data['classes']:
                for day in self.processed_data['days']:
                    for period, _ in self.processed_data['periods']:
                        class_vars = [
                            assignments[key] for key in assignments
                            if key[0] == class_name and key[4] == day and key[5] == period
                        ]
                        if class_vars:
                            model.AddAtMostOne(class_vars)
            
            # 3. Pas de conflit de salle (une salle ne peut pas accueillir deux cours en même temps)
            for room in self.processed_data['rooms']:
                for day in self.processed_data['days']:
                    for period, _ in self.processed_data['periods']:
                        room_vars = [
                            assignments[key] for key in assignments
                            if key[3] == room and key[4] == day and key[5] == period
                        ]
                        if room_vars:
                            model.AddAtMostOne(room_vars)
            
            # 4. Pas de conflit d'enseignant (un enseignant ne peut pas donner deux cours en même temps)
            for teacher in self.processed_data['teachers']:
                for day in self.processed_data['days']:
                    for period, _ in self.processed_data['periods']:
                        teacher_vars = [
                            assignments[key] for key in assignments
                            if key[2] == teacher and key[4] == day and key[5] == period
                        ]
                        if teacher_vars:
                            model.AddAtMostOne(teacher_vars)
            
            # Objectif: Maximiser les cours en matinée (périodes 1 et 2)
            morning_periods = [p for p, w in self.processed_data['periods'] if w in [1, 2]]
            objective_terms = []
            
            # On donne un poids plus élevé aux périodes du matin
            for key, var in assignments.items():
                period = key[5]
                period_weight = next((5 - w for p, w in self.processed_data['periods'] if p == period), 0)
                objective_terms.append(period_weight * var)
            
            if objective_terms:
                model.Maximize(sum(objective_terms))
            else:
                print("Aucune variable pour l'objectif - vérifiez les données d'entrée")
                return False
            
            # Résolution
            print("Résolution du modèle...")
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 60  # Limite de temps pour la résolution
            status = solver.Solve(model)
            
            # Récupération des résultats
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                print(f"\nSolution {'optimale' if status == cp_model.OPTIMAL else 'réalisable'} trouvée avec score: {solver.ObjectiveValue()}")
                
                # Construction de l'emploi du temps
                self.timetable = {}
                for key, var in assignments.items():
                    if solver.Value(var):
                        class_name, course_code, teacher, room, day, period = key
                        
                        # Initialiser la structure si nécessaire
                        if class_name not in self.timetable:
                            self.timetable[class_name] = {}
                        if day not in self.timetable[class_name]:
                            self.timetable[class_name][day] = {}
                        
                        # Stocker les informations du cours
                        self.timetable[class_name][day][period] = {
                            'course': course_code,
                            'teacher': teacher,
                            'room': room,
                            'course_name': self.processed_data['courses'].get(course_code, {}).get('name', 'Inconnu')
                        }
                
                return True
            else:
                print(f"\nAucune solution trouvée. Statut: {status}")
                return False
            
        except Exception as e:
            print(f"Erreur lors de la création du modèle: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def print_timetable(self):
        """Affiche l'emploi du temps dans le terminal"""
        if not self.timetable:
            print("Aucun emploi du temps généré.")
            return
        
        print("\n" + "=" * 80)
        print("                           EMPLOI DU TEMPS")
        print("=" * 80)
        
        for class_name in sorted(self.timetable.keys()):
            print(f"\nClasse: {class_name}")
            print("-" * 80)
            
            # Afficher l'en-tête avec les périodes
            header = "| Jour        |"
            for period, _ in self.processed_data['periods']:
                header += f" {period} |"
            print(header)
            print("-" * 80)
            
            # Afficher les données pour chaque jour
            for day in self.processed_data['days']:
                row = f"| {day:<11} |"
                
                for period, _ in self.processed_data['periods']:
                    if day in self.timetable.get(class_name, {}) and period in self.timetable[class_name].get(day, {}):
                        session = self.timetable[class_name][day][period]
                        cell = f"{session['course']}\n{session['teacher']}\n{session['room']}"
                        row += f" {cell:<13} |"
                    else:
                        row += " ----------- |"
                
                print(row)
            
            print("-" * 80)
        
        print("\n" + "=" * 80)
    
    def generate_pdf(self, filename='timetable.pdf'):
        """Génère un PDF à partir de l'emploi du temps"""
        if not self.timetable:
            print("Aucun emploi du temps à exporter - le PDF ne sera pas généré")
            return False
        
        try:
            doc = SimpleDocTemplate(filename, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            
            # Pour chaque classe
            for class_name in sorted(self.timetable.keys()):
                # Titre
                elements.append(Paragraph(f"Emploi du temps - {class_name}", styles['Title']))
                
                # Préparation des données du tableau
                table_data = []
                
                # En-tête
                header = ['Jour/Période'] + [period for period, _ in self.processed_data['periods']]
                table_data.append(header)
                
                # Données
                for day in self.processed_data['days']:
                    row = [day]
                    for period, _ in self.processed_data['periods']:
                        if day in self.timetable.get(class_name, {}) and period in self.timetable[class_name].get(day, {}):
                            course = self.timetable[class_name][day][period]
                            
                            # Gestion du nom de cours (peut être une liste ou une string)
                            course_name = course['course_name']
                            if isinstance(course_name, list):
                                # Si c'est une liste, prendre le premier élément ou une valeur par défaut
                                display_name = str(course_name[0]) if course_name else "Nom inconnu"
                            else:
                                display_name = str(course_name)
                            
                            # Tronquer si nécessaire
                            truncated_name = (display_name[:20] + '...') if len(display_name) > 20 else display_name
                            
                            cell_content = [
                                course['course'],
                                truncated_name,
                                f"Prof: {course['teacher']}",
                                f"Salle: {course['room']}"
                            ]
                            row.append('\n'.join(cell for cell in cell_content if cell))
                        else:
                            row.append('Aucun cours')
                    table_data.append(row)
                
                # Création du tableau
                if len(table_data) > 1:
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    elements.append(table)
                    elements.append(Paragraph("<br/><br/>", styles['Normal']))
            
            if elements:
                doc.build(elements)
                print(f"PDF généré avec succès: {filename}")
                return True
            else:
                print("Aucune donnée valide pour générer le PDF")
                return False
            
        except Exception as e:
            print(f"Erreur lors de la génération du PDF: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self, generate_pdf=True):
        """Exécute le processus complet de génération d'emploi du temps"""
        print("Début du traitement...")
        
        # Chargement des données
        print("Chargement des données...")
        if not self.load_data():
            return False
        
        # Prétraitement
        print("Prétraitement des données...")
        if not self.preprocess_data():
            return False
        
        # Création et résolution du modèle
        if not self.create_model():
            return False
        
        # Affichage des résultats
        self.print_timetable()
        
        # Génération du PDF (optionnelle)
        if generate_pdf:
            print("\nGénération du PDF...")
            if self.generate_pdf():
                print("Traitement terminé avec succès!")
            else:
                print("Erreur lors de la génération du PDF")
                return False
        
        return True


def main():
    """Fonction principale"""
    generator = TimeTableGenerator()
    generator.run()


if __name__ == '__main__':
    main()
