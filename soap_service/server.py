"""Servicio SOAP interno para consultar solicitudes de adopción.
"""
from spyne import (
    Application, ServiceBase, Integer, Unicode, Boolean, ComplexModel, rpc
)
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server

from app.database import SessionLocal
from app import models


class SolicitudDetalle(ComplexModel):
    """Tipo de respuesta XML publicado en el contrato WSDL."""

    solicitud_id = Integer
    encontrada = Boolean
    interesado_email = Unicode(min_occurs=0, nillable=True)
    animal_id = Integer(min_occurs=0, nillable=True)
    animal_nombre = Unicode(min_occurs=0, nillable=True)
    tipo = Unicode(min_occurs=0, nillable=True)
    estado = Unicode(min_occurs=0, nillable=True)
    error = Unicode(min_occurs=0, nillable=True)


class SolicitudesService(ServiceBase):
    @rpc(Integer, _returns=SolicitudDetalle)
    def ConsultarSolicitud(ctx, solicitud_id):
        db = SessionLocal()
        try:
            solicitud = db.get(models.Solicitud, solicitud_id)
            if solicitud is None:
                return SolicitudDetalle(
                    solicitud_id=solicitud_id,
                    encontrada=False,
                    error="Solicitud no encontrada",
                )

            animal = db.get(models.Animal, solicitud.animal_id)
            return SolicitudDetalle(
                solicitud_id=solicitud.id,
                encontrada=True,
                interesado_email=solicitud.interesado_email,
                animal_id=solicitud.animal_id,
                animal_nombre=animal.nombre if animal else None,
                tipo=solicitud.tipo.value,
                estado=solicitud.estado.value,
                error=None,
            )
        finally:
            db.close()


application = Application(
    [SolicitudesService],
    tns="urn:refugio:solicitudes",
    in_protocol=Soap11(validator="lxml"),
    out_protocol=Soap11(),
)
wsgi_application = WsgiApplication(application)


if __name__ == "__main__":
    make_server("0.0.0.0", 8001, wsgi_application).serve_forever()
