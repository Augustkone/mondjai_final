"""
MONDJAI — Carnet de Depenses Personnelles
Flask + PostgreSQL + Auth + Reset mdp + Budget + Objectifs + Agent IA
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, session)
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timedelta
import calendar
import hashlib
import smtplib
import random
import string
import os
import json
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mondjai_secret_2026')

# ============================================================
#  BASE DE DONNEES
# ============================================================
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://neondb_owner:npg_OwaFRn7C3LMB@ep-shiny-boat-apdc0eo2.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require'
)

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.set_client_encoding('UTF8')
    except Exception:
        try:
            conn.set_client_encoding('WIN1252')
        except Exception:
            pass
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn, cur

def to_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0

# ============================================================
#  SECURITE
# ============================================================
def hasher_mdp(mdp):
    return hashlib.sha256(mdp.encode('utf-8')).hexdigest()

def login_requis(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'utilisateur_id' not in session:
            flash("Connectez-vous pour acceder a cette page.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ============================================================
#  EMAIL
# ============================================================
try:
    from email_config import EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE, SMTP_HOST, SMTP_PORT
except ImportError:
    EMAIL_EXPEDITEUR   = os.environ.get('EMAIL_EXPEDITEUR',   '')
    EMAIL_MOT_DE_PASSE = os.environ.get('EMAIL_MOT_DE_PASSE', '')
    SMTP_HOST          = 'smtp.gmail.com'
    SMTP_PORT          = 587

# Cle API Anthropic pour l'agent IA
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def generer_code():
    return ''.join(random.choices(string.digits, k=6))

def envoyer_email_reset(destinataire, nom, code):
    msg            = MIMEMultipart('alternative')
    msg['Subject'] = f"[Mondjai] Votre code : {code}"
    msg['From']    = EMAIL_EXPEDITEUR
    msg['To']      = destinataire
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px;">
      <h2 style="color:#f59e0b;">Mondjai</h2>
      <p>Bonjour <strong>{nom}</strong>,</p>
      <p>Voici votre code de reinitialisation :</p>
      <div style="text-align:center;margin:2rem 0;">
        <span style="font-size:2.5rem;font-weight:bold;letter-spacing:0.5rem;
                     color:#f59e0b;background:#1e293b;padding:1rem 2rem;
                     border-radius:8px;border:2px solid #f59e0b;">{code}</span>
      </div>
      <p style="color:#94a3b8;">Expire dans <strong>10 minutes</strong>.</p>
      <p style="color:#64748b;font-size:0.8rem;">Mondjai - ISE 2A 2026</p>
    </div>"""
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE)
        s.sendmail(EMAIL_EXPEDITEUR, destinataire, msg.as_string())

def envoyer_email_alerte_budget(destinataire, nom, pourcentage, total, budget, mois_nom):
    """Envoie une alerte email quand le budget est presque atteint."""
    msg            = MIMEMultipart('alternative')
    msg['Subject'] = f"[Mondjai] ⚠️ Alerte budget — {pourcentage:.0f}% utilise"
    msg['From']    = EMAIL_EXPEDITEUR
    msg['To']      = destinataire
    restant        = budget - total
    couleur_barre  = '#ef4444' if pourcentage >= 90 else '#f59e0b'
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px;">
      <h2 style="color:#f59e0b;">Mondjai ⚠️</h2>
      <p>Bonjour <strong>{nom}</strong>,</p>
      <p>Votre budget du mois de <strong>{mois_nom}</strong> est a <strong
         style="color:{couleur_barre};">{pourcentage:.0f}%</strong> de son utilisation.</p>
      <div style="background:#1e293b;border-radius:8px;padding:1rem;margin:1rem 0;">
        <p style="margin:0.3rem 0;">💰 Budget mensuel : <strong>{budget:,.0f} FCFA</strong></p>
        <p style="margin:0.3rem 0;">📊 Depenses actuelles : <strong style="color:{couleur_barre};">{total:,.0f} FCFA</strong></p>
        <p style="margin:0.3rem 0;">🟢 Restant : <strong style="color:#10b981;">{restant:,.0f} FCFA</strong></p>
      </div>
      <div style="background:#1e293b;border-radius:8px;height:12px;overflow:hidden;margin:1rem 0;">
        <div style="background:{couleur_barre};width:{min(pourcentage,100):.0f}%;height:100%;transition:width 0.3s;"></div>
      </div>
      <p>Pensez a ajuster vos depenses pour rester dans les limites de votre budget.</p>
      <p style="color:#64748b;font-size:0.8rem;">Mondjai - ISE 2A 2026</p>
    </div>"""
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE)
        s.sendmail(EMAIL_EXPEDITEUR, destinataire, msg.as_string())

# ============================================================
#  HELPER : recuperer le budget du mois courant
# ============================================================
def get_budget_mois(cur, user_id, mois=None):
    """Retourne le budget du mois (None si non defini)."""
    if mois is None:
        mois = date.today().strftime('%Y-%m')
    cur.execute("""
        SELECT montant_budget, objectif, objectif_montant, seuil_alerte, alerte_envoyee
        FROM budgets
        WHERE utilisateur_id=%s AND mois=%s
    """, (user_id, mois))
    row = cur.fetchone()
    if not row:
        return None
    return {
        'montant_budget':   to_float(row['montant_budget']),
        'objectif':         row['objectif'] or '',
        'objectif_montant': to_float(row['objectif_montant']),
        'seuil_alerte':     int(row['seuil_alerte']),
        'alerte_envoyee':   row['alerte_envoyee'],
    }

# ============================================================
#  AUTHENTIFICATION
# ============================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'utilisateur_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        nom   = request.form.get('nom',          '').strip()
        email = request.form.get('email',         '').strip().lower()
        mdp   = request.form.get('mot_de_passe',  '')
        mdp2  = request.form.get('mot_de_passe2', '')
        erreurs = []
        if not nom:          erreurs.append("Le nom est requis.")
        if '@' not in email: erreurs.append("Email invalide.")
        if len(mdp) < 4:     erreurs.append("Mot de passe trop court (min 4 caracteres).")
        if mdp != mdp2:      erreurs.append("Les mots de passe ne correspondent pas.")
        if not erreurs:
            conn, cur = get_db()
            cur.execute("SELECT id FROM utilisateurs WHERE email = %s", (email,))
            if cur.fetchone():
                erreurs.append("Cet email est deja utilise.")
            else:
                cur.execute("""
                    INSERT INTO utilisateurs (nom, email, mot_de_passe)
                    VALUES (%s, %s, %s) RETURNING id
                """, (nom, email, hasher_mdp(mdp)))
                user = cur.fetchone()
                conn.commit()
                conn.close()
                session['utilisateur_id']  = user['id']
                session['utilisateur_nom'] = nom
                flash(f"Bienvenue {nom} !", 'success')
                return redirect(url_for('index'))
            conn.close()
        for e in erreurs:
            flash(e, 'error')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'utilisateur_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        mdp   = request.form.get('mot_de_passe', '')
        conn, cur = get_db()
        cur.execute("SELECT id, nom, mot_de_passe FROM utilisateurs WHERE email = %s", (email,))
        user = cur.fetchone()
        conn.close()
        if user and user['mot_de_passe'] == hasher_mdp(mdp):
            session['utilisateur_id']  = user['id']
            session['utilisateur_nom'] = user['nom']
            flash(f"Bienvenue {user['nom']} !", 'success')
            return redirect(url_for('index'))
        flash("Email ou mot de passe incorrect.", 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("Vous etes deconnecte.", 'info')
    return redirect(url_for('login'))


@app.route('/mot-de-passe-oublie', methods=['GET', 'POST'])
def mot_de_passe_oublie():
    if request.method == 'GET':
        return render_template('mot_de_passe_oublie.html', etape='saisir_email')

    etape = request.form.get('etape')

    if etape == 'envoyer_code':
        email = request.form.get('email', '').strip().lower()
        conn, cur = get_db()
        cur.execute("SELECT id, nom FROM utilisateurs WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            conn.close()
            flash("Aucun compte trouve avec cet email.", 'error')
            return render_template('mot_de_passe_oublie.html', etape='saisir_email')
        code   = generer_code()
        expiry = datetime.now() + timedelta(minutes=10)
        cur.execute("UPDATE utilisateurs SET reset_code=%s, reset_expiry=%s WHERE email=%s",
                    (code, expiry, email))
        conn.commit()
        conn.close()
        try:
            envoyer_email_reset(email, user['nom'], code)
            flash(f"Code envoye sur {email} !", 'success')
        except Exception as e:
            flash(f"Erreur envoi email : {e}", 'error')
            return render_template('mot_de_passe_oublie.html', etape='saisir_email')
        return render_template('mot_de_passe_oublie.html', etape='saisir_code', email=email)

    if etape == 'verifier_code':
        email = request.form.get('email', '').strip().lower()
        code  = request.form.get('code',  '').strip()
        conn, cur = get_db()
        cur.execute("SELECT reset_code, reset_expiry FROM utilisateurs WHERE email=%s", (email,))
        user = cur.fetchone()
        conn.close()
        if not user or user['reset_code'] != code:
            flash("Code incorrect. Reessayez.", 'error')
            return render_template('mot_de_passe_oublie.html', etape='saisir_code', email=email)
        if user['reset_expiry'] < datetime.now():
            flash("Code expire. Recommencez.", 'error')
            return render_template('mot_de_passe_oublie.html', etape='saisir_email')
        flash("Code correct !", 'success')
        return render_template('mot_de_passe_oublie.html', etape='nouveau_mdp', email=email, code=code)

    if etape == 'changer_mdp':
        email        = request.form.get('email',        '').strip().lower()
        code         = request.form.get('code',         '').strip()
        nouveau_mdp  = request.form.get('nouveau_mdp',  '')
        nouveau_mdp2 = request.form.get('nouveau_mdp2', '')
        conn, cur = get_db()
        cur.execute("SELECT reset_code, reset_expiry FROM utilisateurs WHERE email=%s", (email,))
        user = cur.fetchone()
        if not user or user['reset_code'] != code or user['reset_expiry'] < datetime.now():
            conn.close()
            flash("Session expiree. Recommencez.", 'error')
            return render_template('mot_de_passe_oublie.html', etape='saisir_email')
        if len(nouveau_mdp) < 4:
            conn.close()
            flash("Mot de passe trop court.", 'error')
            return render_template('mot_de_passe_oublie.html', etape='nouveau_mdp', email=email, code=code)
        if nouveau_mdp != nouveau_mdp2:
            conn.close()
            flash("Les mots de passe ne correspondent pas.", 'error')
            return render_template('mot_de_passe_oublie.html', etape='nouveau_mdp', email=email, code=code)
        cur.execute("""
            UPDATE utilisateurs SET mot_de_passe=%s, reset_code=NULL, reset_expiry=NULL
            WHERE email=%s
        """, (hasher_mdp(nouveau_mdp), email))
        conn.commit()
        conn.close()
        flash("Mot de passe modifie ! Connectez-vous.", 'success')
        return redirect(url_for('login'))

    return redirect(url_for('mot_de_passe_oublie'))

# ============================================================
#  TABLEAU DE BORD
# ============================================================
@app.route('/')
@login_requis
def index():
    user_id = session['utilisateur_id']
    mois_courant = date.today().strftime('%Y-%m')
    conn, cur = get_db()

    # --- Stats du mois ---
    cur.execute("""
        SELECT COALESCE(SUM(montant),0) AS total_mois,
               COALESCE(AVG(montant),0) AS moyenne_par_depense,
               COALESCE(SUM(montant)/NULLIF(COUNT(DISTINCT date_depense),0),0) AS moyenne_journaliere,
               COUNT(*) AS nb_depenses,
               COUNT(DISTINCT date_depense) AS nb_jours_actifs
        FROM depenses
        WHERE utilisateur_id=%s
          AND DATE_TRUNC('month',date_depense)=DATE_TRUNC('month',CURRENT_DATE)
    """, (user_id,))
    stats_raw = cur.fetchone()

    cur.execute("""
        SELECT c.id, c.nom AS categorie, c.couleur, c.icone,
               COALESCE(SUM(d.montant),0) AS total, COUNT(d.id) AS nb_depenses
        FROM categories c
        LEFT JOIN depenses d ON d.categorie_id=c.id AND d.utilisateur_id=%s
            AND DATE_TRUNC('month',d.date_depense)=DATE_TRUNC('month',CURRENT_DATE)
        GROUP BY c.id,c.nom,c.couleur,c.icone ORDER BY total DESC
    """, (user_id,))
    totaux_raw = cur.fetchall()

    cur.execute("""
        SELECT date_depense::text AS jour, SUM(montant) AS total
        FROM depenses WHERE utilisateur_id=%s
          AND date_depense >= CURRENT_DATE - INTERVAL '29 days'
        GROUP BY date_depense ORDER BY date_depense
    """, (user_id,))
    evolution_raw = cur.fetchall()

    cur.execute("""
        SELECT d.id,d.montant,d.description,d.date_depense::text,
               c.nom AS categorie,c.couleur,c.icone
        FROM depenses d JOIN categories c ON c.id=d.categorie_id
        WHERE d.utilisateur_id=%s
        ORDER BY d.date_depense DESC,d.created_at DESC LIMIT 5
    """, (user_id,))
    dernieres_raw = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(montant),0) AS total FROM depenses
        WHERE utilisateur_id=%s
          AND DATE_TRUNC('month',date_depense)=DATE_TRUNC('month',CURRENT_DATE)-INTERVAL '1 month'
    """, (user_id,))
    mois_prec = cur.fetchone()

    # --- Budget du mois courant ---
    budget_info = get_budget_mois(cur, user_id, mois_courant)

    conn.close()

    stats = {
        'total_mois':          to_float(stats_raw['total_mois']),
        'moyenne_journaliere': to_float(stats_raw['moyenne_journaliere']),
        'moyenne_par_depense': to_float(stats_raw['moyenne_par_depense']),
        'nb_depenses':         int(stats_raw['nb_depenses']),
        'nb_jours_actifs':     int(stats_raw['nb_jours_actifs']),
    }
    totaux    = [{**dict(r), 'total':   to_float(r['total'])}   for r in totaux_raw]
    evolution = [{**dict(r), 'total':   to_float(r['total'])}   for r in evolution_raw]
    dernieres = [{**dict(r), 'montant': to_float(r['montant'])} for r in dernieres_raw]
    total_prec   = to_float(mois_prec['total'])
    total_actuel = stats['total_mois']
    variation    = round(((total_actuel-total_prec)/total_prec)*100,1) if total_prec>0 else 0

    # --- Calcul alertes budget ---
    alerte_budget = None
    pourcentage_budget = 0
    if budget_info and budget_info['montant_budget'] > 0:
        pourcentage_budget = (total_actuel / budget_info['montant_budget']) * 100
        if pourcentage_budget >= budget_info['seuil_alerte']:
            alerte_budget = {
                'pourcentage': round(pourcentage_budget, 1),
                'restant':     max(0, budget_info['montant_budget'] - total_actuel),
                'critique':    pourcentage_budget >= 100,
            }

    return render_template('index.html',
        stats=stats, totaux=totaux, evolution=evolution, dernieres=dernieres,
        variation=variation, mois_nom=calendar.month_name[date.today().month],
        annee=date.today().year,
        budget_info=budget_info,
        pourcentage_budget=round(pourcentage_budget, 1),
        alerte_budget=alerte_budget,
        mois_courant=mois_courant)

# ============================================================
#  BUDGET & OBJECTIFS
# ============================================================
@app.route('/budget', methods=['GET', 'POST'])
@login_requis
def budget():
    user_id      = session['utilisateur_id']
    mois_courant = date.today().strftime('%Y-%m')
    conn, cur    = get_db()

    if request.method == 'POST':
        montant_budget   = request.form.get('montant_budget', '0').replace(',', '.')
        objectif         = request.form.get('objectif', '').strip()
        objectif_montant = request.form.get('objectif_montant', '0').replace(',', '.')
        seuil_alerte     = request.form.get('seuil_alerte', '80')
        mois_cible       = request.form.get('mois', mois_courant)

        erreurs = []
        try:
            montant_budget = float(montant_budget)
            if montant_budget < 0:
                erreurs.append("Le budget doit etre positif.")
        except ValueError:
            erreurs.append("Montant de budget invalide.")
        try:
            objectif_montant = float(objectif_montant) if objectif_montant else 0.0
        except ValueError:
            objectif_montant = 0.0
        try:
            seuil_alerte = int(seuil_alerte)
            seuil_alerte = max(10, min(100, seuil_alerte))
        except ValueError:
            seuil_alerte = 80

        if not erreurs:
            cur.execute("""
                INSERT INTO budgets (utilisateur_id, mois, montant_budget, objectif,
                                     objectif_montant, seuil_alerte, alerte_envoyee)
                VALUES (%s,%s,%s,%s,%s,%s, FALSE)
                ON CONFLICT (utilisateur_id, mois) DO UPDATE
                  SET montant_budget=EXCLUDED.montant_budget,
                      objectif=EXCLUDED.objectif,
                      objectif_montant=EXCLUDED.objectif_montant,
                      seuil_alerte=EXCLUDED.seuil_alerte,
                      alerte_envoyee=FALSE
            """, (user_id, mois_cible, montant_budget, objectif or None,
                  objectif_montant, seuil_alerte))
            conn.commit()
            flash("Budget et objectifs enregistres !", 'success')
            conn.close()
            return redirect(url_for('budget'))
        for e in erreurs:
            flash(e, 'error')

    # Charger budgets des 6 derniers mois
    cur.execute("""
        SELECT b.mois,
               b.montant_budget,
               b.objectif,
               b.objectif_montant,
               b.seuil_alerte,
               COALESCE(SUM(d.montant),0) AS total_depense
        FROM budgets b
        LEFT JOIN depenses d ON d.utilisateur_id=b.utilisateur_id
            AND TO_CHAR(d.date_depense,'YYYY-MM')=b.mois
        WHERE b.utilisateur_id=%s
        GROUP BY b.mois, b.montant_budget, b.objectif, b.objectif_montant, b.seuil_alerte
        ORDER BY b.mois DESC
        LIMIT 6
    """, (user_id,))
    historique_budgets_raw = cur.fetchall()

    budget_actuel = get_budget_mois(cur, user_id, mois_courant)

    # Total depenses mois courant
    cur.execute("""
        SELECT COALESCE(SUM(montant),0) AS total FROM depenses
        WHERE utilisateur_id=%s
          AND TO_CHAR(date_depense,'YYYY-MM')=%s
    """, (user_id, mois_courant))
    total_actuel = to_float(cur.fetchone()['total'])

    conn.close()

    historique_budgets = []
    for row in historique_budgets_raw:
        b   = dict(row)
        b['montant_budget']   = to_float(b['montant_budget'])
        b['objectif_montant'] = to_float(b['objectif_montant'])
        b['total_depense']    = to_float(b['total_depense'])
        b['pourcentage'] = round(
            (b['total_depense'] / b['montant_budget'] * 100)
            if b['montant_budget'] > 0 else 0, 1
        )
        historique_budgets.append(b)

    pourcentage_actuel = 0
    if budget_actuel and budget_actuel['montant_budget'] > 0:
        pourcentage_actuel = round(total_actuel / budget_actuel['montant_budget'] * 100, 1)

    return render_template('budget.html',
        budget_actuel=budget_actuel,
        total_actuel=total_actuel,
        pourcentage_actuel=pourcentage_actuel,
        historique_budgets=historique_budgets,
        mois_courant=mois_courant,
        mois_nom=calendar.month_name[date.today().month],
        annee=date.today().year)


@app.route('/api/budget-status')
@login_requis
def api_budget_status():
    """API JSON : statut budget du mois courant (pour polling front-end)."""
    user_id      = session['utilisateur_id']
    mois_courant = date.today().strftime('%Y-%m')
    conn, cur    = get_db()

    budget_info = get_budget_mois(cur, user_id, mois_courant)
    cur.execute("""
        SELECT COALESCE(SUM(montant),0) AS total FROM depenses
        WHERE utilisateur_id=%s AND TO_CHAR(date_depense,'YYYY-MM')=%s
    """, (user_id, mois_courant))
    total = to_float(cur.fetchone()['total'])

    if not budget_info or budget_info['montant_budget'] == 0:
        conn.close()
        return jsonify({'has_budget': False})

    budget      = budget_info['montant_budget']
    pourcentage = round(total / budget * 100, 1)
    restant     = max(0, budget - total)
    alerte      = pourcentage >= budget_info['seuil_alerte']

    # Envoi email alerte si seuil franchi et pas encore envoye
    if alerte and not budget_info['alerte_envoyee'] and EMAIL_EXPEDITEUR:
        try:
            cur.execute("SELECT nom, email FROM utilisateurs WHERE id=%s", (user_id,))
            user_row  = cur.fetchone()
            mois_nom  = calendar.month_name[date.today().month]
            envoyer_email_alerte_budget(
                user_row['email'], user_row['nom'],
                pourcentage, total, budget, mois_nom
            )
            cur.execute("""
                UPDATE budgets SET alerte_envoyee=TRUE
                WHERE utilisateur_id=%s AND mois=%s
            """, (user_id, mois_courant))
            conn.commit()
        except Exception:
            pass

    conn.close()
    return jsonify({
        'has_budget':   True,
        'budget':       budget,
        'total':        total,
        'restant':      restant,
        'pourcentage':  pourcentage,
        'seuil':        budget_info['seuil_alerte'],
        'alerte':       alerte,
        'critique':     pourcentage >= 100,
        'objectif':     budget_info['objectif'],
        'objectif_montant': budget_info['objectif_montant'],
    })

# ============================================================
#  AGENT IA — Conseiller financier
# ============================================================
@app.route('/chat-ia')
@login_requis
def chat_ia():
    return render_template('chat_ia.html')


@app.route('/api/chat-ia', methods=['POST'])
@login_requis
def api_chat_ia():
    """
    Endpoint pour l'agent IA. Recoit l'historique du chat + contexte
    financier de l'utilisateur, retourne la reponse de Claude.
    """
    if not ANTHROPIC_API_KEY:
        return jsonify({'error': 'Cle API Anthropic non configuree.'}), 503

    data     = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'Aucun message.'}), 400

    user_id      = session['utilisateur_id']
    mois_courant = date.today().strftime('%Y-%m')
    conn, cur    = get_db()

    # -- Contexte financier personnalise --
    cur.execute("""
        SELECT COALESCE(SUM(montant),0) AS total_mois,
               COUNT(*) AS nb_depenses
        FROM depenses
        WHERE utilisateur_id=%s
          AND DATE_TRUNC('month',date_depense)=DATE_TRUNC('month',CURRENT_DATE)
    """, (user_id,))
    stats_ia = cur.fetchone()

    cur.execute("""
        SELECT c.nom AS categorie, COALESCE(SUM(d.montant),0) AS total
        FROM categories c
        LEFT JOIN depenses d ON d.categorie_id=c.id AND d.utilisateur_id=%s
            AND DATE_TRUNC('month',d.date_depense)=DATE_TRUNC('month',CURRENT_DATE)
        GROUP BY c.nom ORDER BY total DESC LIMIT 5
    """, (user_id,))
    top_cats = cur.fetchall()

    budget_info = get_budget_mois(cur, user_id, mois_courant)
    cur.execute("SELECT nom FROM utilisateurs WHERE id=%s", (user_id,))
    user_row = cur.fetchone()
    conn.close()

    total_mois = to_float(stats_ia['total_mois'])
    budget_txt = "non defini"
    objectif_txt = "non defini"
    if budget_info:
        budget_txt = f"{budget_info['montant_budget']:,.0f} FCFA"
        if budget_info['objectif']:
            objectif_txt = f"{budget_info['objectif']} ({budget_info['objectif_montant']:,.0f} FCFA)"
    cats_txt = ", ".join(
        f"{r['categorie']} ({to_float(r['total']):,.0f} FCFA)"
        for r in top_cats if to_float(r['total']) > 0
    ) or "aucune depense ce mois"

    system_prompt = f"""Tu es Mondjai IA, un conseiller financier personnel bienveillant et expert,
integre dans l'application Mondjai de gestion des depenses personnelles.

PROFIL DE L'UTILISATEUR (mois en cours) :
- Nom            : {user_row['nom']}
- Total depense  : {total_mois:,.0f} FCFA
- Nombre depenses: {int(stats_ia['nb_depenses'])}
- Budget mensuel : {budget_txt}
- Objectif       : {objectif_txt}
- Top categories : {cats_txt}

TES INSTRUCTIONS :
1. Reponds toujours en francais, de facon claire, concise et amicale.
2. Utilise les donnees financielles ci-dessus pour personnaliser tes conseils.
3. Tu peux donner des conseils sur : economies, budgetisation, reduction des depenses,
   investissement debutant, objectifs financiers.
4. Si l'utilisateur depasse ou risque de depasser son budget, alerte-le avec empathie
   et propose des solutions concretes.
5. Ne fournis jamais de conseils medicaux, juridiques ou politiques.
6. Reste toujours positif et motivant.
7. Limite tes reponses a 3-4 paragraphes maximum pour rester lisible.
8. Les montants sont en FCFA (franc CFA ouest-africain).
"""

    payload = json.dumps({
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system":     system_prompt,
        "messages":   messages
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result      = json.loads(resp.read().decode('utf-8'))
            answer_text = result['content'][0]['text']
        return jsonify({'response': answer_text})
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        return jsonify({'error': f"Erreur API : {body}"}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
#  AJOUTER
# ============================================================
@app.route('/ajouter', methods=['GET', 'POST'])
@login_requis
def ajouter():
    conn, cur = get_db()
    cur.execute("SELECT id,nom,icone FROM categories ORDER BY nom")
    categories = cur.fetchall()
    if request.method == 'POST':
        montant      = request.form.get('montant','').replace(',','.')
        description  = request.form.get('description','').strip()
        categorie_id = request.form.get('categorie_id')
        date_str     = request.form.get('date_depense', str(date.today()))
        erreurs = []
        try:
            montant = float(montant)
            if montant <= 0: erreurs.append("Le montant doit etre positif.")
        except ValueError:
            erreurs.append("Montant invalide.")
        if not categorie_id: erreurs.append("Veuillez choisir une categorie.")
        if erreurs:
            for e in erreurs: flash(e, 'error')
        else:
            cur.execute("""
                INSERT INTO depenses (montant,description,categorie_id,date_depense,utilisateur_id)
                VALUES (%s,%s,%s,%s,%s)
            """, (montant, description or None, categorie_id, date_str, session['utilisateur_id']))
            conn.commit()
            flash(f"Depense de {montant:,.0f} FCFA ajoutee !", 'success')

            # Verifier si le budget est atteint apres l'ajout
            user_id      = session['utilisateur_id']
            mois_courant = date.today().strftime('%Y-%m')
            budget_info  = get_budget_mois(cur, user_id, mois_courant)
            if budget_info and budget_info['montant_budget'] > 0:
                cur.execute("""
                    SELECT COALESCE(SUM(montant),0) AS total FROM depenses
                    WHERE utilisateur_id=%s AND TO_CHAR(date_depense,'YYYY-MM')=%s
                """, (user_id, mois_courant))
                total_now   = to_float(cur.fetchone()['total'])
                pct         = total_now / budget_info['montant_budget'] * 100
                if pct >= budget_info['seuil_alerte'] and not budget_info['alerte_envoyee']:
                    if EMAIL_EXPEDITEUR:
                        try:
                            cur.execute("SELECT nom,email FROM utilisateurs WHERE id=%s", (user_id,))
                            u = cur.fetchone()
                            envoyer_email_alerte_budget(
                                u['email'], u['nom'], pct, total_now,
                                budget_info['montant_budget'],
                                calendar.month_name[date.today().month]
                            )
                            cur.execute("""
                                UPDATE budgets SET alerte_envoyee=TRUE
                                WHERE utilisateur_id=%s AND mois=%s
                            """, (user_id, mois_courant))
                            conn.commit()
                        except Exception:
                            pass
            conn.close()
            return redirect(url_for('index'))
    conn.close()
    return render_template('ajouter.html', categories=categories, aujourd_hui=str(date.today()))

# ============================================================
#  HISTORIQUE
# ============================================================
@app.route('/historique')
@login_requis
def historique():
    user_id = session['utilisateur_id']
    conn, cur = get_db()
    mois     = request.args.get('mois',      date.today().strftime('%Y-%m'))
    cat_id   = request.args.get('categorie', '')
    page     = max(1, int(request.args.get('page', 1)))
    par_page = 15
    params = [user_id, mois+'-01']
    where  = ["d.utilisateur_id=%s",
              "DATE_TRUNC('month',d.date_depense)=DATE_TRUNC('month',%s::date)"]
    if cat_id:
        where.append("d.categorie_id=%s")
        params.append(cat_id)
    where_sql = " AND ".join(where)
    cur.execute(f"SELECT COUNT(*) AS n FROM depenses d WHERE {where_sql}", params)
    total    = cur.fetchone()['n']
    nb_pages = max(1, -(-total // par_page))
    offset   = (page-1)*par_page
    cur.execute(f"""
        SELECT d.id,d.montant,d.description,d.date_depense::text,
               c.nom AS categorie,c.couleur,c.icone
        FROM depenses d JOIN categories c ON c.id=d.categorie_id
        WHERE {where_sql} ORDER BY d.date_depense DESC,d.created_at DESC
        LIMIT %s OFFSET %s
    """, params+[par_page, offset])
    depenses_raw = cur.fetchall()
    cur.execute(f"SELECT COALESCE(SUM(d.montant),0) AS total FROM depenses d WHERE {where_sql}", params)
    total_filtre = to_float(cur.fetchone()['total'])
    cur.execute("SELECT id,nom,icone FROM categories ORDER BY nom")
    categories = cur.fetchall()
    conn.close()
    depenses = [{**dict(r), 'montant': to_float(r['montant'])} for r in depenses_raw]
    return render_template('historique.html',
        depenses=depenses, categories=categories,
        mois=mois, cat_id=cat_id, page=page, nb_pages=nb_pages,
        total=total, total_filtre=total_filtre)

# ============================================================
#  SUPPRIMER / MODIFIER
# ============================================================
@app.route('/supprimer/<int:dep_id>', methods=['POST'])
@login_requis
def supprimer(dep_id):
    conn, cur = get_db()
    cur.execute("DELETE FROM depenses WHERE id=%s AND utilisateur_id=%s",
                (dep_id, session['utilisateur_id']))
    conn.commit()
    conn.close()
    flash("Depense supprimee.", 'info')
    return redirect(request.referrer or url_for('historique'))


@app.route('/modifier/<int:dep_id>', methods=['GET', 'POST'])
@login_requis
def modifier(dep_id):
    conn, cur = get_db()
    cur.execute("SELECT id,nom,icone FROM categories ORDER BY nom")
    categories = cur.fetchall()
    cur.execute("""
        SELECT d.*,c.nom AS categorie_nom
        FROM depenses d JOIN categories c ON c.id=d.categorie_id
        WHERE d.id=%s AND d.utilisateur_id=%s
    """, (dep_id, session['utilisateur_id']))
    dep_raw = cur.fetchone()
    if not dep_raw:
        conn.close()
        flash("Depense introuvable.", 'error')
        return redirect(url_for('historique'))
    if request.method == 'POST':
        montant      = request.form.get('montant','').replace(',','.')
        description  = request.form.get('description','').strip()
        categorie_id = request.form.get('categorie_id')
        date_str     = request.form.get('date_depense')
        try:
            montant = float(montant)
            cur.execute("""
                UPDATE depenses SET montant=%s,description=%s,categorie_id=%s,date_depense=%s
                WHERE id=%s AND utilisateur_id=%s
            """, (montant, description or None, categorie_id, date_str,
                  dep_id, session['utilisateur_id']))
            conn.commit()
            flash("Depense mise a jour !", 'success')
            conn.close()
            return redirect(url_for('historique'))
        except ValueError:
            flash("Montant invalide.", 'error')
    conn.close()
    dep = {**dict(dep_raw), 'montant': to_float(dep_raw['montant'])}
    return render_template('modifier.html', dep=dep, categories=categories)

# ============================================================
#  LANCEMENT
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
