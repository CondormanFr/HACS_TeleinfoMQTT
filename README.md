
# Téléinfo Gateway (HA custom integration)

- Lit la Téléinfo sur un port série (1200 7E1 par défaut)
- Crée des entités natives (PAPP, IINST, IMAX, index en kWh) **après réception de la première trame**
- Ajoute un capteur **Statut Téléinfo** qui compte les trames (utile pour diagnostiquer)
- **Optionnel :** publie sur MQTT (`teleinfo/line`, `/json`, `/fields`, `/invalid`, `/derived`)
- **Optionnel :** publie les topics **MQTT Discovery** pour autodécouverte côté HA

## Installation (HACS)
1. HACS → Integrations → menu ⋮ → *Custom repositories* → URL du repo → Category: *Integration* → Add
2. Installer *Téléinfo Gateway*, redémarrer HA.
3. Paramétrer le port série et les options MQTT dans l'UI.

## Notes
- Pour l’Energy Dashboard, les index Wh sont convertis en kWh côté entité.
- Les capteurs discovery publiés pointent vers vos topics MQTT (`teleinfo/…`).
