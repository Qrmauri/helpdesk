class Usuario:
    """
    Representa un usuario del sistema HelpDesk.
    
    Roles disponibles:
    - PUBLICADOR: Crea tickets
    - AGENTE: Atiende tickets asignados
    - SUPERVISOR: Gestiona configuración y todos los tickets
    """
    
    # Constantes de roles
    PUBLICADOR = 'PUBLICADOR'
    AGENTE = 'AGENTE'
    SUPERVISOR = 'SUPERVISOR'
    
    def __init__(self, id, username, email, password_hash, role):
        self.id = id
        self.username = username
        self.email = email
        self.__password_hash = password_hash  # Atributo privado
        self.role = role.upper()
        if self.role not in (self.PUBLICADOR, self.AGENTE, self.SUPERVISOR):
            raise ValueError("Rol de usuario inválido.")
    
    @property
    def password_hash(self):
        """Getter para password_hash (solo lectura desde fuera)"""
        return self.__password_hash
    
    def es_publicador(self):
        """Verifica si el usuario es publicador"""
        return self.role == self.PUBLICADOR
    
    def es_agente(self):
        """Verifica si el usuario es agente"""
        return self.role == self.AGENTE
    
    def es_supervisor(self):
        """Verifica si el usuario es supervisor"""
        return self.role == self.SUPERVISOR
    
    def puede_asignar_tickets(self):
        """Solo supervisores pueden asignar tickets a agentes"""
        return self.es_supervisor()
    
    def puede_ver_todos_los_tickets(self):
        """Solo supervisores pueden ver todos los tickets"""
        return self.es_supervisor()
    
    def puede_reabrir_tickets(self):
        """Solo supervisores pueden reabrir tickets cerrados"""
        return self.es_supervisor()
    
    def __str__(self):
        """Representación en texto del usuario"""
        return f"Usuario({self.username}, {self.role})"
    
    def __repr__(self):
        return self.__str__()
