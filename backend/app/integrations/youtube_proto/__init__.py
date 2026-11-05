"""Google's Apache-2.0 streaming sample; see LICENSE and stream_list.proto attribution.

Regenerate from backend/ after uv sync --locked (grpcio-tools is dev-only):

    uv run python -m grpc_tools.protoc -I. --python_out=. --pyi_out=. \
        --grpc_python_out=. app/integrations/youtube_proto/stream_list.proto

The grpc_tools CLI supplies its bundled google/protobuf include directory.
"""
