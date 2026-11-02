# TCL Lyon – Prochains départs pour Home Assistant

Intégration Home Assistant qui affiche les prochains départs des bus, trams et métros TCL
(Lyon) en temps réel. Elle comprend une carte Lovelace **plein écran**, conçue pour une
tablette murale (testée sur la résolution d'un Echo Show 8 sous LineageOS, 1280×800).

- Configuration 100 % via l'interface : recherche d'arrêt, puis choix des lignes **et des directions**.
- **Alertes trafic** (travaux, perturbations) affichées sous chaque ligne concernée.
- **Stations Vélo'v** : vélos disponibles (dont électriques) et places libres.
- Un capteur par ligne/direction suivie (valeur = minutes avant le prochain départ).
- La carte `tcl-departures-card` est chargée automatiquement, sans ressource à ajouter.
- Le compte à rebours se met à jour toutes les 10 s entre deux rafraîchissements de l'API (20 s).

## 1. Accès aux données (gratuit)

Les données temps réel TCL sont publiées par la Métropole de Lyon, en **accès restreint** :

1. Crée un compte sur <https://data.grandlyon.com>.
2. Ouvre le jeu de données **« Prochains passages temps réel du réseau TCL »**
   (`tcl_sytral.tclpassagearret`) et clique sur **Demander l'accès**.
   L'accès est en général accordé rapidement (quelques heures à quelques jours).
3. Fais de même pour **« Alertes trafic du réseau TCL (v2) »** (`tcl_sytral.tclalertetrafic_2`).
   Ce jeu est facultatif : sans lui, le module fonctionne, mais sans les alertes.
4. Le jeu **Vélo'v** (`jcd_jcdecaux.jcdvelov`) est en accès libre.
5. Tu utiliseras ensuite l'email et le mot de passe de ce compte dans Home Assistant.

## 2. Installation

### Via HACS (recommandé)
1. HACS → menu ⋮ → **Dépôts personnalisés** → ajoute l'URL de ce dépôt, catégorie **Intégration**.
2. Installe **TCL Lyon - Prochains départs**, puis redémarre Home Assistant.

### Manuelle
Copie `custom_components/tcl_lyon` dans le dossier `config/custom_components/` de Home Assistant, puis redémarre.

## 3. Configuration

1. **Paramètres → Appareils et services → Ajouter une intégration → TCL Lyon**, puis saisis tes identifiants data.grandlyon.com.
2. Sur l'intégration, clique sur **Configurer → Ajouter un arrêt / des lignes** :
   - tape le nom de l'arrêt (ex. `Bellecour`) ;
   - choisis le quai : chaque sens a souvent son propre numéro d'arrêt ;
   - coche les lignes et directions à afficher. Les directions proposées viennent des
     prochains passages réels. La nuit, utilise « toutes directions » ou reviens en journée.
3. Recommence pour d'autres arrêts. **Configurer → Ajouter une station Vélo'v** permet d'ajouter des
   stations Vélo'v, et **Configurer → Retirer** permet d'enlever des éléments.

Chaque ligne suivie crée un capteur, par exemple `sensor.arret_tcl_bellecour_c20_toutes_directions`, avec ces attributs :
`ligne`, `direction`, `arret`, `departs` (liste de `heure`, `minutes`, `temps_reel`, `direction`),
`alertes` (liste de `titre`, `message`, `debut`, `fin`).

Chaque station Vélo'v crée un capteur `sensor.velo_v_<station>_velos_disponibles`, avec les attributs
`places`, `capacite`, `velos_electriques`, `velos_mecaniques` et `statut`.

Rafraîchissements : passages toutes les 20 s, Vélo'v toutes les 60 s, alertes toutes les 5 min.

## 4. Tableau de bord plein écran

Crée un nouveau tableau de bord (ex. « Bus »), passe en mode édition → **Éditeur YAML** et colle :

```yaml
views:
  - title: Bus
    path: bus
    type: panel
    cards:
      - type: custom:tcl-departures-card
        title: Prochains départs
```

Sans liste `entities`, la carte affiche **tous** les capteurs TCL, triés par prochain départ,
avec les stations Vélo'v en bas.

Options :

| Option | Défaut | Description |
|---|---|---|
| `title` | `Prochains départs` | Titre en haut à gauche |
| `entities` | toutes | Liste de capteurs à afficher |
| `sort` | `time` | `time` (prochain départ d'abord) ou `config` (ordre de `entities`) |
| `max_departures` | `3` | Nombre de départs par ligne |
| `fullscreen` | `true` | Recouvre tout l'écran, y compris la barre et le menu HA |
| `show_clock` | `true` | Affiche l'heure |
| `show_stop` | `true` | Affiche le nom de l'arrêt sous la direction |
| `hide_empty` | `false` | Masque les lignes sans départ prévu |
| `show_alerts` | `true` | Affiche les alertes trafic sous la ligne, à la place du nom de l'arrêt |
| `colors` | – | Couleurs personnalisées, ex. `{ "86": "#0090d0" }` |

Exemple avec une sélection :

```yaml
      - type: custom:tcl-departures-card
        title: Arrêt Gare de Vaise
        max_departures: 4
        sort: config
        entities:
          - sensor.arret_tcl_gare_de_vaise_c14_toutes_directions
          - sensor.arret_tcl_gare_de_vaise_31_toutes_directions
```

En mode `fullscreen`, l'édition du tableau devient difficile. Pour modifier la carte, passe
par l'éditeur YAML du tableau, ou ouvre l'URL avec `?edit=1`.

## 5. Sur l'Echo Show 8 (LineageOS)

- Affiche l'URL `http://<ha>:8123/dashboard-bus/bus` avec **Fully Kiosk Browser** ou l'app
  **Home Assistant Companion** (Paramètres → Companion app → *Garder l'écran allumé*).
- Avec Fully Kiosk, active *Keep Screen On*, *Start on boot* et la réduction de luminosité la nuit.

## Notes

- Le point vert ● indique un horaire **temps réel**. Sans ce point, l'horaire est théorique.
- Données : TCL / SYTRAL Mobilités via data.grandlyon.com.
