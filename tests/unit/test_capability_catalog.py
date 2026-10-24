import pytest
from quentin.capabilities.catalog import CapabilityCatalog, Capability, CapabilityType, LifecycleStatus
from quentin.capabilities.lifecycle_manager import LifecycleManager

def test_capability_catalog_registration():
    catalog = CapabilityCatalog()
    cap = Capability(name="test_tool", type=CapabilityType.TOOL)
    catalog.register(cap)
    
    assert catalog.get(cap.id) == cap
    assert len(catalog.list_all()) == 1

def test_lifecycle_promotion():
    catalog = CapabilityCatalog()
    manager = LifecycleManager(catalog)
    cap = Capability(name="test_tool", status=LifecycleStatus.EXPERIMENTAL)
    catalog.register(cap)
    
    success = manager.promote(cap.id)
    assert success
    assert cap.status == LifecycleStatus.TRUSTED

def test_lifecycle_retire():
    catalog = CapabilityCatalog()
    manager = LifecycleManager(catalog)
    cap = Capability(name="test_tool", status=LifecycleStatus.TRUSTED)
    catalog.register(cap)
    
    success = manager.retire(cap.id)
    assert success
    assert cap.status == LifecycleStatus.RETIRED
