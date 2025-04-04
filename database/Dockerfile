FROM postgres:15

COPY init.sql /docker-entrypoint-initdb.d/

ENV POSTGRES_DB=tododb
ENV POSTGRES_USER=admin
ENV POSTGRES_PASSWORD=admin123

EXPOSE 5432 