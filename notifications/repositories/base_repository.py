"""
BaseRepositoryBuilder
---------------------

Repositorio genérico para operaciones CRUD comunes.

La intención de esta abstracción es evitar duplicar lógica repetitiva
(get, all, save, delete, etc.) en cada modelo. Sin embargo, si un modelo
requiere operaciones de base de datos específicas (ej. filtros o queries
que se usaran varias veces), esas deben implementarse en su propio
repositorio especializado, heredando de esta base.

De esta forma:
- La lógica genérica vive aquí.
- La lógica específica de cada modelo vive en su respectivo repositorio.
"""

from typing import ClassVar, Generic, List, Optional, Type, TypeVar, Union

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model as BaseModel
from django.db.models import Q, QuerySet

T = TypeVar("T", bound=BaseModel)
SimplePK = Union[int, str]


class BaseRepositoryBuilder(Generic[T]):
    """
    Repositorio base para operaciones CRUD.

    - Por defecto retorna `list` para resultados inmediatos.
    - Con `as_queryset=True` retorna `QuerySet` si se requiere.

        - `list`: ejecuta la query al instante y carga resultados en memoria.
        - `QuerySet`: evaluación diferida, permite encadenar mas filtros/ordenamientos.
    """

    __model__: ClassVar[Type[T]]
    __pk_field__: ClassVar[str] = "pk"

    @classmethod
    def get_by_id(cls, primary_key: SimplePK) -> Optional[T]:
        """Obtiene un registro por ID. Devuelve None si no existe."""
        try:
            return cls.__model__.objects.get(**{cls.__pk_field__: primary_key})
        except ObjectDoesNotExist:
            return None

    @classmethod
    def get_all(cls, as_queryset: bool = False) -> Union[List[T], QuerySet[T]]:
        """
        Retorna todos los registros.

        Args:
            as_queryset: Si True devuelve QuerySet, si False devuelve list.
        """
        queryset = cls.__model__.objects.all()
        return queryset if as_queryset else list(queryset)

    @classmethod
    def get_model(cls) -> Type[T]:
        """Devuelve la clase del modelo asociado al repositorio."""
        return cls.__model__

    @classmethod
    def save_record(cls, instance: T) -> T:
        """Guarda (crea o actualiza) una instancia del modelo."""
        instance.save()
        return instance

    @classmethod
    def delete_record(cls, instance: T) -> bool:
        """Elimina una instancia del modelo."""
        instance.delete()
        return True

    @classmethod
    def find_records(
        cls,
        field_order: Optional[str] = None,
        first: bool = False,
        q_object: Optional[Q] = None,
        as_queryset: bool = False,
        **filter_input,
    ) -> Union[T, List[T], QuerySet[T], None]:
        """
        Busca registros con filtros dinámicos.

        Args:
            field_order: Campo para ordenar.
            first: Si True retorna solo el primer resultado.
            q_object: Filtros complejos con Q().
            as_queryset: Si True devuelve QuerySet, si False devuelve list.

        Returns:
            - Modelo si `first=True`
            - list[Modelo] o QuerySet[Modelo] según `as_queryset`
            - None si no hay resultados
        """
        queryset = cls.__model__.objects.all()

        if q_object:
            queryset = queryset.filter(q_object)

        if filter_input:
            queryset = queryset.filter(**filter_input)

        if field_order:
            queryset = queryset.order_by(field_order)

        if first:
            return queryset.first()

        return queryset if as_queryset else list(queryset)
