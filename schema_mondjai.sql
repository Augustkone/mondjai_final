-- ============================================================
--  MONDJAI -- Schema PostgreSQL complet
--  Executer dans pgAdmin > Query Tool sur depenses_db
-- ============================================================

-- Nettoyage complet (remet a zero si besoin)
DROP TABLE IF EXISTS depenses     CASCADE;
DROP TABLE IF EXISTS categories   CASCADE;
DROP TABLE IF EXISTS utilisateurs CASCADE;

-- ============================================================
--  TABLE 1 : utilisateurs
-- ============================================================
CREATE TABLE utilisateurs (
    id            SERIAL       PRIMARY KEY,
    nom           VARCHAR(100) NOT NULL,
    email         VARCHAR(150) NOT NULL UNIQUE,
    mot_de_passe  VARCHAR(255) NOT NULL,
    reset_code    VARCHAR(6),
    reset_expiry  TIMESTAMP,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- ============================================================
--  TABLE 2 : categories
-- ============================================================
CREATE TABLE categories (
    id      SERIAL      PRIMARY KEY,
    nom     VARCHAR(50) NOT NULL UNIQUE,
    couleur VARCHAR(7)  NOT NULL DEFAULT '#6b7280',
    icone   VARCHAR(10) NOT NULL DEFAULT '?'
);

-- ============================================================
--  TABLE 3 : depenses
-- ============================================================
CREATE TABLE depenses (
    id             SERIAL        PRIMARY KEY,
    montant        NUMERIC(12,2) NOT NULL CHECK (montant > 0),
    description    VARCHAR(255),
    categorie_id   INTEGER       NOT NULL REFERENCES categories(id)   ON DELETE RESTRICT,
    utilisateur_id INTEGER       NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    date_depense   DATE          NOT NULL DEFAULT CURRENT_DATE,
    created_at     TIMESTAMP     DEFAULT NOW()
);

-- ============================================================
--  INDEX
-- ============================================================
CREATE INDEX idx_dep_user      ON depenses(utilisateur_id);
CREATE INDEX idx_dep_date      ON depenses(date_depense);
CREATE INDEX idx_dep_categorie ON depenses(categorie_id);

-- ============================================================
--  8 CATEGORIES PAR DEFAUT
-- ============================================================
INSERT INTO categories (nom, couleur, icone) VALUES
('Alimentation', '#f59e0b', '🍽'),
('Transport',    '#3b82f6', '🚗'),
('Logement',     '#8b5cf6', '🏠'),
('Sante',        '#10b981', '💊'),
('Loisirs',      '#ec4899', '🎉'),
('Vetements',    '#f97316', '👕'),
('Education',    '#14b8a6', '📚'),
('Autres',       '#6b7280', '📦');

-- ============================================================
--  VERIFICATION FINALE
-- ============================================================
SELECT 'utilisateurs' AS table_name, COUNT(*) AS lignes FROM utilisateurs
UNION ALL
SELECT 'categories',  COUNT(*) FROM categories
UNION ALL
SELECT 'depenses',    COUNT(*) FROM depenses;
