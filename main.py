from containers import setup_container


def main():
    # El contenedor lee automáticamente las variables de entorno vía config.py
    container = setup_container()

    # Obtener la instancia del Agente
    agent = container.agent()

    # Iniciar flujo
    prompt = "¿Recuerdas mis preferencias?"
    agent.prepare_system_prompt(prompt)
    print("Agente iniciado exitosamente con configuración validada.")


if __name__ == "__main__":
    main()