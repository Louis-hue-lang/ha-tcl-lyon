# TCL Lyon – Prochains départs pour Home Assistant

Intégration Home Assistant qui affiche les prochains départs des bus, trams et métros TCL
(Lyon) en temps réel. Elle comprend une carte Lovelace **plein écran**, conçue pour une
tablette murale (testée sur la résolution d'un Echo Show 8 sous LineageOS, 1280×800).

- Configuration 100 % via l'interface : recherche d'arrêt, puis choix des lignes **et des directions**.
- **Alertes trafic** (travaux, perturbations) affichées sous chaque ligne concernée.
- **Stations Vélo'v** : vélos disponibles (dont électriques) et places libres.
- **Carte des bus** (bus et trams) : touche une ligne pour ouvrir une carte avec les bus qui **arrivent vers ton
  arrêt**. Le cadrage s'adapte pour en montrer un maximum, et l'orientation de la carte se règle.
- Un capteur par ligne/direction suivie (valeur = minutes avant le prochain départ).
- La carte `tcl-departures-card` est chargée automatiquement, sans ressource à ajouter.
- Le compte à rebours se met à jour toutes les 10 s entre deux rafraîchissements de l'API (20 s).

## 1. Accès aux données (gratuit)

Les données temps réel TCL sont publiées par la Métropole de Lyon, en **accès restreint** :

1. Crée un compte sur <https://data.grandlyon.com>.
2. Ouvre le jeu de données **« Prochains passages temps réel du réseau TCL »**
   (`tcl_sytral.tclpassagearret`) et clique sur **Demander l'accès**.
   L'accès est en général accordé rapidement (quelques heures à quelques jours).
3. Facultatif, mais recommandé : demande aussi l'accès à ces jeux. Sans eux, la fonction correspondante est simplement désactivée.
   - **« Alertes trafic du réseau TCL (v2) »** (`tcl_sytral.tclalertetrafic_2`)
   - **« Alertes trafic des lignes scolaires »** (`jd_juniordirect.jdalertetrafic_2`)
   - **« Positions en temps réel des véhicules »** (flux SIRI Lite `vehicle-monitoring`), pour la carte des bus
4. Le jeu **Vélo'v** est en accès libre.
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

Rafraîchissements : passages toutes les 20 s, Vélo'v toutes les 2 min, alertes toutes les 5 min.
Les positions des bus ne sont téléchargées **que pendant que la carte est ouverte**, toutes les 20 s.
Le flux pèse environ 600 Ko : un téléchargement permanent représenterait près de 3 Go par jour.

### Carte des bus

**Configurer → Carte des bus (réglages)** :
- **URL de l'API des positions** : par défaut, le flux SIRI Lite de data.grandlyon.com. Vide le champ pour désactiver la carte.
- **Orientation de la carte** : un angle fixe. 0° met le nord en haut, 90° l'est, etc. Choisis-le pour que
  tes bus arrivent par le haut de l'écran, par exemple.

Pour sélectionner les bus qui **arrivent vers ton arrêt**, le module utilise, du plus fiable au moins fiable :
1. **la course** : la course du véhicule dans le flux SIRI (`DatedVehicleJourneyRef`) a le même format que le champ
   `coursetheorique` des prochains passages. Si la course figure dans les passages annoncés à ton arrêt, le bus
   y va forcément et n'y est pas encore passé. Il s'affiche en couleur pleine.
2. **la destination** (`DestinationRef` / `idtarretdestination`) : les bus qui vont dans l'autre sens sont écartés ;
3. pour les autres bus du bon sens, plus loin que les passages annoncés : l'évolution de leur distance à l'arrêt,
   puis leur cap. Ils s'affichent en semi-transparent.

Le métro et le funiculaire ne figurent pas dans le flux de positions. La carte l'indique.

Le cadrage englobe l'arrêt et ces bus. L'arrêt se retrouve donc dans un coin, et le reste de l'écran
montre la zone d'où ils arrivent. La fenêtre se ferme avec ✕, ou toute seule après 60 s sans contact.

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
| `popup_timeout` | `60` | Secondes avant la fermeture automatique de la carte (`0` = jamais) |
| `map_style` | `dark` | Fond de carte : `dark` (CARTO sombre) ou `light` (OpenStreetMap) |
| `map_bearing` | – | Force une orientation, en ignorant le réglage de l'intégration |

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

## Légèreté (pensé pour un Echo Show 8 de 1re génération)

Côté écran (carte Lovelace) :
- elle ne se redessine que si un capteur TCL a changé, et non à chaque changement d'état de la maison ;
- le DOM n'est modifié que si le texte affiché change. Le compte à rebours est recalculé toutes les 15 s ;
- aucune animation permanente ;
- la carte des bus utilise Leaflet (150 Ko, sans WebGL). Elle n'est chargée qu'à la première ouverture,
  reste statique (ni glisser, ni zoom) et est libérée à la fermeture.

Côté Home Assistant :
- passages filtrés par arrêt côté serveur quand c'est possible. Sinon, tout le réseau est téléchargé et l'intervalle passe à 60 s ;
- positions des bus (environ 600 Ko) téléchargées seulement pendant que la carte est ouverte ;
- liste complète des arrêts libérée dès que les coordonnées utiles sont connues.

## Et l'intégration officielle « Data Grand Lyon » ?

Home Assistant intègre aussi, depuis peu, une intégration officielle [Data Grand Lyon](https://www.home-assistant.io/integrations/data_grand_lyon).
Les deux peuvent coexister. Ce module va plus loin pour un écran de départs :

| | Data Grand Lyon (officielle) | Ce module |
|---|---|---|
| Prochains départs | 3, par arrêt et par ligne | jusqu'à 6, par ligne et direction |
| Rafraîchissement | 5 min | 20 s, avec compte à rebours entre deux mises à jour |
| Vélo'v | ✅ | ✅ |
| Parcs relais | ✅ | ❌ |
| Alertes trafic (TCL et scolaires) | ❌ | ✅ |
| Carte des bus en approche | ❌ | ✅ |
| Carte plein écran | ❌ | ✅ |

## Notes

- La carte utilise [Leaflet](https://leafletjs.com/) (licence BSD), fourni avec le module.
  Les fonds de carte se chargent depuis Internet.
- Tests : `pip install pytest-homeassistant-custom-component`, puis `pytest`.

- Le point vert ● indique un horaire **temps réel**. Sans ce point, l'horaire est théorique.
- Données : TCL / SYTRAL Mobilités via data.grandlyon.com.
